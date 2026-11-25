"""Exclusive, fail-closed local desktop session and durable halt state.

Only the desktop owner invokes resume; worker threads observe a cooperative
threading.Event. The OS lock is held until workers have drained and close
returns. No external authorization or automatic task replay.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, get_ident
import os

from .event_store import EventStore
from .council_attempts import CouncilAttemptStore
from .scenario_council import ScenarioCouncil
from .dashboard_events import project
from .scout import _timestamp

_REASONS={"halted":{"startup","emergency","shutdown"},
          "offline_ready":{"explicit_resume"}}
MAX_REVISION=1000000000


def _lock(path):
    handle=path.open("a+b")
    try:
        handle.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        elif os.name=="posix":
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        else:
            raise OSError("unsupported local locking platform")
        return handle
    except BaseException:
        handle.close()
        raise


class RuntimeGuard:
    """One cooperating application per trusted local data directory."""
    def __init__(self,directory,*,clock=None):
        self._stop=Event()
        self._stop.set()
        self._faulted=False
        self._closed=False
        self._owner_thread=get_ident()
        self._council_active=False
        self._operator_active=False
        self._browser_active=False
        self._browser_job=None
        self._browser_executor=None
        self.council_recovered_count=0
        self.council_escalated_count=0
        self._clock=clock or (lambda:datetime.now(timezone.utc))
        directory=Path(directory).resolve()
        self._directory=directory
        directory.mkdir(parents=True,exist_ok=True)
        try:
            self._lock=_lock(directory/"runtime.lock")
        except OSError:
            raise PermissionError("Exclusive local application ownership unavailable.") from None
        self.events=None
        try:
            self.events=EventStore(directory/"events.sqlite3")
            self.events.db.execute("PRAGMA synchronous=FULL")
            self.events.db.execute("""CREATE TABLE IF NOT EXISTS runtime_guard_v1(
                slot INTEGER PRIMARY KEY CHECK(slot=1),state TEXT NOT NULL,
                reason TEXT NOT NULL,revision INTEGER NOT NULL,changed_at TEXT NOT NULL)""")
            self._persist("halted","startup")
            self.recovered_count=self.events.recover_interrupted(now=self._clock())
            self.recover_council()
        except BaseException:
            try:
                if self.events is not None:
                    self.events.close()
            finally:
                self._lock.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.close()

    def is_set(self):
        return self._stop.is_set()

    def _require_owner(self):
        if self._closed or self._lock.closed or get_ident()!=self._owner_thread:
            raise PermissionError("exclusive runtime owner thread required")

    def _require_idle(self):
        self._require_owner()
        if (self._council_active or self._operator_active or self._browser_active
                or project(self.events.read())["tasks"]):
            raise PermissionError("active worker must drain before local maintenance")

    def _council_path(self):
        path=self._directory/"council.sqlite3"
        if not os.path.lexists(path):
            return None
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid local Council database path")
        return path

    def _council_pending(self):
        path=self._council_path()
        if path is None:
            return 0
        with CouncilAttemptStore(path,existing_only=True) as store:
            return store._runtime_pending(now=self._clock())

    def recover_council(self):
        """Halted maintenance only, under actual exclusive local ownership.

        The desktop caller must also ensure its worker future has drained.
        Never run predicates, dispatch, or clear the halt during recovery.
        """
        self._require_idle()
        if self._faulted or not self.is_set():
            raise PermissionError("halted healthy runtime required for Council recovery")
        try:
            path=self._council_path()
            if path is None:
                return dict(recovered=0,escalated=0)
            with CouncilAttemptStore(path,existing_only=True) as store:
                result=store._runtime_recover_all(now=self._clock())
            self.council_recovered_count+=result["recovered"]
            self.council_escalated_count+=result["escalated"]
            return result
        except BaseException:
            self._stop.set()
            self._faulted=True
            raise

    def council_action(self,action,plan_id):
        """Explicit owner-thread local action for an exact saved scenario.

        This is a trusted desktop facade, not an arbitrary agent callback.
        The desktop must additionally exclude any unjournaled worker future.
        """
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Council unavailable while halted or faulted")
        if type(action) is not str or action not in ("inspect","register","run_once","history"):
            raise ValueError("unsupported Council action")
        self._council_active=True
        try:
            adapter=ScenarioCouncil(self._directory,halt_check=self.is_set,clock=self._clock)
            operations={"inspect":adapter.inspect,"register":adapter.register,
                        "run_once":adapter.run_once,"history":adapter.history}
            if action=="run_once" and self._council_pending():
                self.set()
                raise PermissionError("outstanding Council reservation requires halted recovery")
            result=operations[action](plan_id)
            if self.is_set():
                raise PermissionError("Council result withheld after halt")
            return result
        except BaseException:
            # A failed review may have reserved an attempt. Do not allow a
            # subsequent call to silently dispatch another until recovery.
            if action=="run_once" and not self.is_set():
                try:
                    if self._council_pending():
                        self.set()
                except BaseException:
                    self._stop.set()
                    self._faulted=True
            raise
        finally:
            self._council_active=False

    def operator_action(self,action,plan_id,**inputs):
        """Fixed local draft operations, owner thread only; no recipient dispatch."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Operator unavailable while halted or faulted")
        fields={"prepare":{"supplier","region","items"},"save":{"supplier","region","items"},
                "history":{"draft_id"},"history_list":{"limit"},
                "acknowledge":{"draft_id","supplier","confirmed"},
                "recipient_preview":{"draft_id","supplier","recipient","evidence_path"},
                "recipient_save":{"draft_id","supplier","recipient","evidence_path","expected_recipient_id","confirmed"},
                "recipient_history":{"draft_id","limit"}}
        if type(action) is not str or action not in fields or set(inputs)!=fields[action]:
            raise ValueError("unsupported Operator action or inputs")
        from .operator_scenarios import OperatorScenario
        self._operator_active=True
        try:
            adapter=OperatorScenario(self._directory,halt_check=self.is_set,clock=self._clock)
            operations={"prepare":adapter.prepare,"save":adapter.save,
                        "history":adapter.history,"history_list":adapter.history_list,
                        "acknowledge":adapter.acknowledge,
                        "recipient_preview":adapter.recipient_preview,"recipient_save":adapter.recipient_save,
                        "recipient_history":adapter.recipient_history}
            result=operations[action](plan_id,**inputs)
            if self.is_set():
                raise PermissionError("Operator result withheld after halt")
            return result
        finally:
            self._operator_active=False

    def _csv_ready(self,confirmed):
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Operator unavailable while halted or faulted")
        if confirmed is not True:
            raise PermissionError("explicit local deliverable confirmation required")

    def _csv_snapshot(self,plan_id):
        if self._council_pending():
            self.set()
            raise PermissionError("outstanding Council reservation requires halted recovery")
        return ScenarioCouncil(self._directory,halt_check=self.is_set,
                               clock=self._clock).inspect(plan_id)

    def _csv_scoped(self,plan_id,raw,specification,*,snapshot=None):
        from .digital_deliverable import build_contract, produce_csv
        if snapshot is None:
            snapshot=self._csv_snapshot(plan_id)
        contract=build_contract(snapshot,specification,halted=self.is_set())
        result=produce_csv(contract,raw,halted=self.is_set(),halt_check=self.is_set)
        current=self._csv_snapshot(plan_id)
        if (current["context"]!=snapshot["context"] or
                current["scenario_sha256"]!=snapshot["scenario_sha256"] or
                current["schedule_sha256"]!=snapshot["schedule_sha256"] or
                current["source_hold"] is not None):
            raise ValueError("deliverable scenario scope changed")
        if self.is_set():
            raise PermissionError("deliverable withheld after halt")
        return result

    def produce_csv_deliverable(self,plan_id,*,raw,specification,confirmed=None):
        """One explicit local, bounded work sample for an exact saved plan."""
        self._csv_ready(confirmed)
        self._operator_active=True
        try:
            return self._csv_scoped(plan_id,raw,specification)
        finally:
            self._operator_active=False

    def csv_file_action(self,action,plan_id,*,confirmed=None,**inputs):
        """Fixed local preview/export actions; no arbitrary callback or external dispatch."""
        self._csv_ready(confirmed)
        fields={"preview":{"source_path","columns","key_column","expected_rows"},
                "export":{"source_path","columns","key_column","expected_rows",
                          "destination_path","expected_contract","expected_report","expected_artifact"}}
        if type(action) is not str or action not in fields or set(inputs)!=fields[action]:
            raise ValueError("unsupported CSV action or inputs")
        from .digital_deliverable import build_contract
        from .deliverable_files import read_selected_csv, publish_new_csv, preview_pins
        from .checklist_store import _hash
        from hashlib import sha256
        self._operator_active=True
        try:
            snapshot=self._csv_snapshot(plan_id)
            if action=="export":
                for key in ("expected_contract","expected_report","expected_artifact"):
                    _hash(inputs[key])
            # Validate the declared schema and current source before file I/O.
            spec=dict(input_sha256="0"*64,columns=inputs["columns"],
                      key_column=inputs["key_column"],expected_rows=inputs["expected_rows"])
            build_contract(snapshot,spec,halted=self.is_set())
            raw=read_selected_csv(inputs["source_path"],halted=self.is_set(),halt_check=self.is_set)
            spec["input_sha256"]=sha256(raw).hexdigest()
            result=self._csv_scoped(plan_id,raw,spec,snapshot=snapshot)
            if action=="preview":
                return result
            pins=preview_pins(result)
            if any(pins[key]!=inputs[key] for key in pins):
                raise ValueError("CSV preview changed; preview again before export")
            publish_new_csv(inputs["destination_path"],result["artifact"],
                            halted=self.is_set(),halt_check=self.is_set)
            if self.is_set():
                raise PermissionError("halt after publication; inspect selected destination")
            return dict(pins,exported=True,report=result["report"],
                        buyer_accepted=False,external_authority=False)
        finally:
            self._operator_active=False

    def browser_fixture(self,fixture_id,*,confirmed=None):
        """Fixed, explicit local diagnostics; no caller URL, plan, clock or callback."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Scout diagnostics unavailable while halted or faulted")
        if confirmed is not True:
            raise PermissionError("explicit local fixture confirmation required")
        from .browser_contract import plan_fixture
        from .browser_fixture_runner import _run_fixture
        plan=plan_fixture(fixture_id,request_limit=2,timeout_ms=5000,halted=self.is_set())
        self._browser_active=True
        try:
            if self._council_pending():
                self.set()
                raise PermissionError("outstanding Council reservation requires halted recovery")
            result=_run_fixture(plan,halted=self.is_set(),halt_check=self.is_set)
            if self.is_set():
                raise PermissionError("Scout diagnostic result withheld after halt")
            return result
        except BaseException:
            if not self.is_set():
                try:
                    self.set()
                except BaseException:
                    self._stop.set()
                    self._faulted=True
            raise
        finally:
            self._browser_active=False

    def browser_process_pending(self):
        """Owner-thread state; remains true until the supervisor is collected."""
        self._require_owner()
        return self._browser_job is not None

    def _browser_process_fault(self):
        if not self.is_set():
            try:
                self.set()
            except BaseException:
                self._stop.set()
                self._faulted=True

    def start_browser_process(self,fixture_id,*,confirmed=None):
        """Reserve and launch one fixed offline diagnostic; never accept a Future or callback."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Scout diagnostics unavailable while halted or faulted")
        if confirmed is not True:
            raise PermissionError("explicit local fixture confirmation required")
        from .browser_contract import plan_fixture
        from .browser_process import _supervise, DEFAULT_PARENT_MS
        plan=plan_fixture(fixture_id,request_limit=2,timeout_ms=5000,halted=self.is_set())
        self._browser_active=True
        try:
            if self._council_pending():
                self.set()
                raise PermissionError("outstanding Council reservation requires halted recovery")
            self._browser_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="scout-fixture")
            # The worker only receives the fixed plan and the thread-safe halt reader.
            # It cannot use the owner's SQLite connection or change runtime state.
            self._browser_job=self._browser_executor.submit(
                _supervise,plan,halt_check=self.is_set,timeout_ms=DEFAULT_PARENT_MS)
        except BaseException:
            try:
                if self._browser_executor is not None:
                    self._browser_executor.shutdown(wait=True,cancel_futures=True)
            finally:
                self._browser_executor=None
                self._browser_job=None
                self._browser_active=False
                self._browser_process_fault()
            raise

    def _collect_browser_process(self,*,wait):
        self._require_owner()
        job=self._browser_job
        if job is None:
            raise PermissionError("no reserved Scout diagnostic")
        if not wait and not job.done():
            return None
        try:
            report=job.result()
            if self.is_set():
                raise PermissionError("Scout diagnostic result withheld after halt")
            return report
        except BaseException as exc:
            from .browser_process import ProcessDenied
            self._browser_process_fault()
            if isinstance(exc,ProcessDenied) and exc.reason=="WORKER_CLEANUP_FAILED":
                self._faulted=True
            raise
        finally:
            # No idle/close/resume until supervisor thread has joined.
            self._browser_executor.shutdown(wait=True,cancel_futures=True)
            self._browser_executor=None
            self._browser_job=None
            self._browser_active=False

    def poll_browser_process(self):
        """Nonblocking owner collection; None means still reserved/running."""
        return self._collect_browser_process(wait=False)

    def drain_browser_process(self):
        """Shutdown-only collection; never release a result while halted."""
        self._require_owner()
        if not self.is_set():
            raise PermissionError("halt before draining Scout diagnostic")
        if self._browser_job is None:
            return
        try:
            self._collect_browser_process(wait=True)
        except Exception:
            # The halt remains asserted; no result or automatic replay.
            if self._browser_job is not None:
                raise

    def _read(self):
        rows=self.events.db.execute(
            "SELECT slot,state,reason,revision,changed_at FROM runtime_guard_v1").fetchall()
        if not rows:
            return None
        if len(rows)!=1:
            raise ValueError("invalid runtime state cardinality")
        slot,state,reason,revision,stamp=rows[0]
        if (slot!=1 or type(state) is not str or state not in _REASONS
                or type(reason) is not str or reason not in _REASONS[state]
                or type(revision) is not int or not 1<=revision<=MAX_REVISION
                or type(stamp) is not str
                or _timestamp(stamp).isoformat(timespec="microseconds")!=stamp):
            raise ValueError("invalid persisted runtime state")
        return dict(state=state,reason=reason,revision=revision,changed_at=stamp)

    def status(self):
        if self._closed:
            raise PermissionError("runtime closed")
        previous=self._read()
        if previous is None:
            raise ValueError("runtime state missing")
        return dict(previous,persisted_state=previous["state"],
            state="halted" if self.is_set() else previous["state"],
            reason="persistence_fault" if self._faulted else previous["reason"],
            council_recovered_count=self.council_recovered_count,
            council_escalated_count=self.council_escalated_count,external_authority=False)

    def _persist(self,state,reason):
        now=self._clock()
        if type(now) is not datetime or now.utcoffset() is None:
            raise ValueError("aware runtime clock required")
        stamp=now.astimezone(timezone.utc).isoformat(timespec="microseconds")
        db=self.events.db
        db.execute("BEGIN IMMEDIATE")
        try:
            old=self._read()
            if old is None and reason!="startup":
                raise ValueError("runtime state missing")
            if old is not None and _timestamp(old["changed_at"])>_timestamp(stamp):
                raise ValueError("runtime clock moved backward")
            revision=1 if old is None else old["revision"]+1
            if revision>MAX_REVISION:
                raise ValueError("runtime revision limit reached")
            db.execute("""INSERT INTO runtime_guard_v1 VALUES (1,?,?,?,?)
                ON CONFLICT(slot) DO UPDATE SET state=excluded.state,reason=excluded.reason,
                revision=excluded.revision,changed_at=excluded.changed_at""",
                (state,reason,revision,stamp))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise

    def set(self):
        # Cooperative cancellation must precede disk operations.
        self._stop.set()
        self._require_owner()
        try:
            self._persist("halted","emergency")
        except BaseException:
            self._faulted=True
            raise

    def resume(self):
        self._require_idle()
        if self._faulted:
            raise PermissionError("runtime unavailable; restart and recover")
        if not self._stop.is_set():
            return
        try:
            if self._council_pending():
                raise PermissionError("unfinished Council reservations require halted recovery")
            self._persist("offline_ready","explicit_resume")
        except PermissionError:
            raise
        except BaseException:
            self._faulted=True
            raise
        self._stop.clear()

    def close(self):
        if self._closed:
            return
        self._require_owner()
        if self._council_active or self._operator_active or self._browser_active:
            raise PermissionError("Local Council, Operator or Scout action must drain before close")
        self._stop.set()
        try:
            self._persist("halted","shutdown")
        finally:
            self._closed=True
            try:
                self.events.close()
            finally:
                self._lock.close()
