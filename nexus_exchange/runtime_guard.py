"""Exclusive, fail-closed local desktop session and durable halt state.

Only the desktop owner invokes resume; worker threads observe a cooperative
threading.Event. The OS lock is held until workers have drained and close
returns. No external authorization or automatic task replay.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, get_ident
from uuid import uuid4
import os

from .event_store import EventStore
from . import advisory_launch_marker as launch_marker
from .council_attempts import CouncilAttemptStore
from .advisory_attempts import AdvisoryAttemptStore, DB_NAME as ADVISORY_DB
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
        self._advisory_active=False
        self._advisory_job=None
        self._advisory_executor=None
        self._advisory_reservation=None
        self._advisory_preview=None
        self.council_recovered_count=0
        self.council_escalated_count=0
        self.advisory_recovered_count=0
        self.advisory_escalated_count=0
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
            launch_marker.initialize(self.events.db)
            self.events.db.execute("""CREATE TABLE IF NOT EXISTS runtime_guard_v1(
                slot INTEGER PRIMARY KEY CHECK(slot=1),state TEXT NOT NULL,
                reason TEXT NOT NULL,revision INTEGER NOT NULL,changed_at TEXT NOT NULL)""")
            self._persist("halted","startup")
            self.recovered_count=self.events.recover_interrupted(now=self._clock())
            self.recover_council()
            if launch_marker.pending(self.events.db):
                # The previous owner did not prove its child drained. A new
                # OS lock proves exclusive ownership, not process-tree death.
                self._faulted=True
            else:
                self.recover_advisory()
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
        if (self._council_active or self._operator_active or self._browser_active or self._advisory_active
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

    def _advisory_path(self):
        path=self._directory/ADVISORY_DB
        if not os.path.lexists(path):
            return None
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid local advisory database path")
        return path

    def _advisory_pending(self):
        path=self._advisory_path()
        if path is None:
            return 0
        with AdvisoryAttemptStore(path,existing_only=True) as store:
            return store._runtime_pending(now=self._clock())

    def recover_advisory(self):
        """Reconcile ledger reservations under halted owner-thread/idle lock.

        The active synthetic supervisor must be collected before maintenance.
        The desktop additionally excludes unjournaled worker futures.
        """
        self._require_idle()
        if self._faulted or not self.is_set():
            raise PermissionError("halted healthy runtime required for advisory recovery")
        try:
            if launch_marker.pending(self.events.db):
                raise PermissionError("advisory process cleanup unconfirmed; quarantine retained")
            path=self._advisory_path()
            if path is None:
                return dict(recovered=0,escalated=0)
            with AdvisoryAttemptStore(path,existing_only=True) as store:
                result=store._runtime_recover_all(now=self._clock())
            self.advisory_recovered_count+=result["recovered"]
            self.advisory_escalated_count+=result["escalated"]
            return result
        except BaseException:
            self._stop.set()
            self._faulted=True
            raise

    def advisory_process_pending(self):
        """Owner-only observation of an outstanding synthetic supervisor."""
        self._require_owner()
        return self._advisory_job is not None

    def _advisory_fault(self, *, uncertain=False):
        if not self.is_set():
            try:
                self.set()
            except BaseException:
                self._stop.set()
                self._faulted=True
        if uncertain:
            self._faulted=True

    def prepare_advisory_process(self,plan_id):
        """Owner-only, one-use in-memory consent preview; no ledger or child created."""
        self._require_idle()
        self._advisory_preview=None
        if self._faulted or self.is_set():
            raise PermissionError("Advisory unavailable while halted or faulted")
        if launch_marker.pending(self.events.db) or self._council_pending() or self._advisory_pending():
            raise PermissionError("outstanding reservation requires halted recovery")
        original=ScenarioCouncil(self._directory,halt_check=self.is_set,
                                 clock=self._clock).inspect(plan_id)
        path=self._advisory_path()
        budget=dict(state="NOT_STARTED",attempts_used=0,next_attempt=1)
        if path is not None:
            with AdvisoryAttemptStore(path,existing_only=True) as store:
                budget=store.preview_budget(plan_id,halted=self.is_set())
        if budget["next_attempt"] is None or self.is_set():
            raise PermissionError("advisory attempt unavailable")
        from .advisory_process import FIXTURE_MODEL_SHA256
        from .local_advisory import build_request
        # Validate the complete bounded request before offering consent.
        build_request(original,FIXTURE_MODEL_SHA256,budget["next_attempt"],
                      now=self._clock(),approved=True,halted=self.is_set())
        preview_id=uuid4().hex
        self._advisory_preview=(preview_id,original,budget["next_attempt"],self._read()["revision"])
        return dict(preview_id=preview_id,plan_id=plan_id,next_attempt=budget["next_attempt"],
                    snapshot_sha256=original["snapshot_sha256"],synthetic_only=True,
                    external_authority=False,dispatch_enabled=False)

    def start_prepared_advisory_process(self,plan_id,preview_id,*,confirmed=None):
        """Consume exactly one owner-held preview; no automatic retries."""
        self._require_idle()
        prepared=self._advisory_preview
        self._advisory_preview=None
        if (confirmed is not True or type(preview_id) is not str or prepared is None
                or preview_id!=prepared[0] or plan_id!=prepared[1]["plan_id"]
                or self._faulted or self.is_set() or self._read()["revision"]!=prepared[3]):
            raise PermissionError("fresh explicit synthetic advisory consent required")
        return self._start_advisory_process(plan_id,confirmed=True,prepared=prepared)

    def start_advisory_process(self,plan_id,*,confirmed=None):
        """Trusted headless diagnostic path; native controls must use a preview."""
        self._require_idle()
        self._advisory_preview=None
        return self._start_advisory_process(plan_id,confirmed=confirmed,prepared=None)

    def _start_advisory_process(self,plan_id,*,confirmed,prepared):
        """Reserve one fixed synthetic advisory attempt, never actual inference."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Advisory unavailable while halted or faulted")
        if confirmed is not True:
            raise PermissionError("explicit local advisory confirmation required")
        from .advisory_process import FIXTURE_MODEL_SHA256, DEFAULT_PARENT_MS, _supervise
        self._advisory_active=True
        armed=False
        try:
            if launch_marker.pending(self.events.db):
                raise PermissionError("previous advisory cleanup unconfirmed")
            if self._council_pending() or self._advisory_pending():
                raise PermissionError("outstanding reservation requires halted recovery")
            original=ScenarioCouncil(self._directory,halt_check=self.is_set,
                                     clock=self._clock).inspect(plan_id)
            if self.is_set():
                raise PermissionError("advisory halted before reservation")
            expected_attempt=None
            if prepared is not None:
                from .advisory_current_scope import _compare_scope, _stamp
                before=prepared[1]
                _compare_scope(before,original,created=_stamp(before["evaluated_at"]),now=self._clock())
                expected_attempt=prepared[2]
            path=self._advisory_path()
            with AdvisoryAttemptStore(path or self._directory/ADVISORY_DB,
                                      existing_only=path is not None) as store:
                reserved=store.reserve(original,FIXTURE_MODEL_SHA256,now=self._clock(),
                                       approved=True,halted=self.is_set(),expected_attempt=expected_attempt)
            self._advisory_reservation=(original,reserved)
            # Commit BEFORE even submitting the worker. Crash between marker
            # and launch is intentionally a conservative false-positive hold.
            launch_marker.arm(self.events.db,reserved["ticket"]["reservation_id"])
            armed=True
            self._advisory_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="advisory-fixture")
            self._advisory_job=self._advisory_executor.submit(
                _supervise,reserved["request"],halt_check=self.is_set,timeout_ms=DEFAULT_PARENT_MS)
            return dict(reserved["ticket"],external_authority=False)
        except BaseException:
            self._advisory_fault(uncertain=armed)
            if self._advisory_executor is not None:
                self._advisory_executor.shutdown(wait=True,cancel_futures=True)
            self._advisory_executor=None
            self._advisory_job=None
            self._advisory_reservation=None
            self._advisory_active=False
            raise

    def _collect_advisory_process(self,*,wait):
        self._require_owner()
        job=self._advisory_job
        if job is None:
            raise PermissionError("no reserved advisory process")
        if not wait and not job.done():
            return None
        from .advisory_process import ProcessDenied
        cleanup_confirmed=False
        try:
            original,reserved=self._advisory_reservation
            token=reserved["ticket"]["reservation_id"]
            try:
                report=job.result()
            except ProcessDenied as exc:
                self._advisory_executor.shutdown(wait=True,cancel_futures=True)
                # Only these known supervisor exits establish either no launch
                # or a successful finally-cleanup. Unknown and start/identity
                # failures remain quarantined, even if the thread has joined.
                if exc.reason in ("HALTED_OR_UNKNOWN","WORKER_DEADLINE",
                                  "WORKER_EXIT_FAILED","RESULT_SIZE","INVALID_RESPONSE"):
                    launch_marker.clear(self.events.db,token)
                    cleanup_confirmed=True
                raise
            # A future becoming done is not enough: join its supervisor before
            # checking fresh scope or passing the ledger's worker_drained flag.
            self._advisory_executor.shutdown(wait=True,cancel_futures=True)
            launch_marker.clear(self.events.db,token)
            cleanup_confirmed=True
            if self.is_set():
                raise PermissionError("advisory result withheld after halt")
            current=ScenarioCouncil(self._directory,halt_check=self.is_set,
                                    clock=self._clock).inspect(reserved["ticket"]["plan_id"])
            if self.is_set():
                raise PermissionError("advisory halted before completion")
            path=self._advisory_path()
            if path is None:
                raise ValueError("advisory reservation database missing")
            with AdvisoryAttemptStore(path,existing_only=True) as store:
                result=store.complete_current(reserved["ticket"],reserved["request"],
                    original,current,report["response"],now=self._clock(),
                    approved=True,halted=self.is_set(),worker_drained=True)
            if self.is_set():
                raise PermissionError("advisory result withheld after halt")
            return result
        except BaseException:
            self._advisory_fault(uncertain=not cleanup_confirmed)
            raise
        finally:
            self._advisory_executor.shutdown(wait=True,cancel_futures=True)
            self._advisory_executor=None
            self._advisory_job=None
            self._advisory_reservation=None
            self._advisory_active=False

    def poll_advisory_process(self):
        """Nonblocking owner collection; None means still reserved."""
        return self._collect_advisory_process(wait=False)

    def drain_advisory_process(self):
        """Halted shutdown collection, with no result publication or replay."""
        self._require_owner()
        if not self.is_set():
            raise PermissionError("halt before draining advisory process")
        if self._advisory_job is None:
            return
        try:
            self._collect_advisory_process(wait=True)
        except Exception:
            if self._advisory_job is not None:
                raise

    def council_action(self,action,plan_id):
        """Explicit owner-thread local action for an exact saved scenario.

        This is a trusted desktop facade, not an arbitrary agent callback.
        The desktop must additionally exclude any unjournaled worker future.
        """
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Council unavailable while halted or faulted")
        if type(action) is not str or action not in ("inspect","register","run_once","history","advisory_status"):
            raise ValueError("unsupported Council action")
        self._council_active=True
        try:
            adapter=ScenarioCouncil(self._directory,halt_check=self.is_set,clock=self._clock)
            operations={"inspect":adapter.inspect,"register":adapter.register,
                        "run_once":adapter.run_once,"history":adapter.history}
            if action=="run_once" and self._council_pending():
                self.set()
                raise PermissionError("outstanding Council reservation requires halted recovery")
            if action=="advisory_status":
                snapshot=adapter.inspect(plan_id)
                path=self._advisory_path()
                budget=dict(state="NOT_STARTED",attempts_used=0,next_attempt=1)
                if path is not None:
                    with AdvisoryAttemptStore(path,existing_only=True) as store:
                        budget=store.preview_budget(plan_id,halted=self.is_set())
                result=dict(budget,plan_id=snapshot["plan_id"],task_id=snapshot["task_id"],
                    historical_only=True,current_decision=False,independently_verified=False,
                    dispatch_enabled=False,external_authority=False,execution_eligible=False,
                    commercial_facts_verified=False,release_eligible=False)
            else:
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
                "recipient_history":{"draft_id","limit"},
                "thread_history":{"draft_id","recipient_id"},
                "thread_open":{"draft_id","recipient_id","supplier","confirmed"},
                "thread_append":{"draft_id","recipient_id","supplier","kind","evidence_path","expected_head","expected_evidence","confirmed"}}
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
                        "recipient_history":adapter.recipient_history,
                        "thread_history":adapter.thread_history,"thread_open":adapter.thread_open,
                        "thread_append":adapter.thread_append}
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

    def _csv_scoped(self,plan_id,raw,specification,*,snapshot=None,source_format="UTF8_CSV",operation="PRESERVE",right_raw=None):
        from .digital_deliverable import build_contract, produce_csv
        if snapshot is None:
            snapshot=self._csv_snapshot(plan_id)
        contract=build_contract(snapshot,specification,halted=self.is_set(),source_format=source_format,operation=operation)
        result=produce_csv(contract,raw,halted=self.is_set(),halt_check=self.is_set,right_raw=right_raw)
        current=self._csv_snapshot(plan_id)
        if build_contract(current,specification,halted=self.is_set(),source_format=source_format,operation=operation)!=contract:
            raise ValueError("deliverable scenario scope changed")
        if self.is_set():
            raise PermissionError("deliverable withheld after halt")
        return result

    def produce_csv_deliverable(self,plan_id,*,raw,specification,confirmed=None,source_format="UTF8_CSV",operation="PRESERVE",right_raw=None):
        """One explicit local, bounded work sample for an exact saved plan."""
        self._csv_ready(confirmed)
        self._operator_active=True
        try:
            return self._csv_scoped(plan_id,raw,specification,source_format=source_format,operation=operation,right_raw=right_raw)
        finally:
            self._operator_active=False

    def produce_scoped_service_sample(self,plan_id,*,context,requirements,expected_scope,
                                      raw,confirmed=None,right_raw=None):
        """Explicit transient local sample from caller-supplied authorized bytes."""
        self._csv_ready(confirmed)
        self._operator_active=True
        try:
            return self._scoped_service_sample(plan_id,context,requirements,expected_scope,
                                               raw=raw,right_raw=right_raw)
        finally:
            self._operator_active=False

    def preview_scoped_service_files(self,plan_id,*,context,requirements,expected_scope,
                                     source_path,right_source_path=None,confirmed=None):
        """Read only explicitly selected local files after fresh scoped preflight."""
        self._csv_ready(confirmed)
        self._operator_active=True
        try:
            return self._scoped_service_sample(plan_id,context,requirements,expected_scope,
                file_paths=(source_path,right_source_path))
        finally:
            self._operator_active=False

    def export_scoped_service_files(self,plan_id,*,context,requirements,expected_scope,
                                    source_path,destination_path,expected_pins,
                                    right_source_path=None,confirmed=None):
        """Reproduce the exact reviewed sample and publish one new local CSV."""
        from .scoped_export import checked_export_pins, require_matching_pins
        from .deliverable_files import preview_pins, publish_new_csv
        self._csv_ready(confirmed)
        pinned=checked_export_pins(expected_pins)
        self._operator_active=True
        try:
            result=self._scoped_service_sample(plan_id,context,requirements,expected_scope,
                file_paths=(source_path,right_source_path))
            if result["review_scope_sha256"]!=expected_scope or result["external_authority"] is not False:
                raise ValueError("SCOPED_PREVIEW_CHANGED")
            sample=result["sample"]
            pins=require_matching_pins(pinned,preview_pins(sample))
            publish_new_csv(destination_path,sample["artifact"],
                            halted=self.is_set(),halt_check=self.is_set)
            if self.is_set():
                raise PermissionError("halt after publication; inspect selected destination")
            return dict(pins,review_scope_sha256=expected_scope,exported=True,
                        buyer_accepted=False,external_authority=False)
        finally:
            self._operator_active=False

    def register_scoped_service_files(self,plan_id,*,context,requirements,expected_scope,
                                      source_path,artifact_path,expected_pins,
                                      right_source_path=None,confirmed=None):
        """Register one selected matching artifact with immutable Scout provenance."""
        from .scoped_export import checked_export_pins, require_matching_pins
        from .deliverable_files import preview_pins
        from .deliverable_obligations import ObligationStore, artifact_reference
        from .evidence import verify_reference
        from .ranking_workspace import RankingWorkspace
        from .service_handoff import checked_review_route
        from .scoped_provenance import build_provenance
        from .digital_deliverable import build_contract
        self._csv_ready(confirmed)
        pinned=checked_export_pins(expected_pins)
        self._operator_active=True
        try:
            result=self._scoped_service_sample(plan_id,context,requirements,expected_scope,
                file_paths=(source_path,right_source_path))
            if result["review_scope_sha256"]!=expected_scope or result["external_authority"] is not False:
                raise ValueError("SCOPED_PREVIEW_CHANGED")
            sample=result["sample"]
            require_matching_pins(pinned,preview_pins(sample))
            match=verify_reference(artifact_path,artifact_reference(sample),
                                   halted=self.is_set(),halt_check=self.is_set)
            if match["byte_match"] is not True:
                raise ValueError("selected artifact does not match reviewed deliverable")
            # Revalidate after the artifact read. Do not store caller-supplied
            # review material or infer current authority from a historical pin.
            snapshot=self._csv_snapshot(plan_id)
            review=RankingWorkspace(self._directory,halt_check=self.is_set,clock=self._clock).review_requirements(context,requirements)
            source,operation=checked_review_route(review,expected_scope,snapshot["context"])
            if build_contract(snapshot,sample["contract"]["specification"],halted=self.is_set(),
                    source_format=source,operation=operation)!=sample["contract"]:
                raise ValueError("deliverable scenario scope changed")
            provenance=build_provenance(review,expected_scope,sample["contract"],sample["report"])
            path=self._directory/"operator-obligations.sqlite3"
            with ObligationStore(path,existing_only=os.path.lexists(path)) as store:
                return store.register(sample,now=self._clock(),confirmed=True,
                    halted=self.is_set(),halt_check=self.is_set,scout_review=provenance)
        finally:
            self._operator_active=False

    def _scoped_service_sample(self,plan_id,context,requirements,expected_scope,
                               *,raw=None,right_raw=None,file_paths=None):
        from .ranking_workspace import RankingWorkspace
        from .service_handoff import checked_review_route, checked_sample_inputs
        from .digital_deliverable import build_contract, _input, _right_input, DeliverableError
        workspace=RankingWorkspace(self._directory,halt_check=self.is_set,clock=self._clock)
        snapshot=self._csv_snapshot(plan_id)
        review=workspace.review_requirements(context,requirements)

        def recheck_review():
            current=workspace.review_requirements(context,requirements)
            checked_review_route(current,expected_scope,snapshot["context"])
            if self.is_set():
                raise PermissionError("deliverable withheld after halt")
            return current

        if file_paths is not None:
            from .deliverable_files import read_selected_csv
            source,operation=checked_review_route(review,expected_scope,snapshot["context"])
            source_path,right_path=file_paths
            if (operation=="RECONCILE")!=(right_path is not None):
                raise ValueError("EXACT_SELECTED_INPUT_COUNT_REQUIRED")
            # Validate the current saved-plan contract before touching a file.
            build_contract(snapshot,review["requirements_assessment"]["declared_input"]["specification"],
                halted=self.is_set(),source_format=source,operation=operation)
            raw=read_selected_csv(source_path,halted=self.is_set(),halt_check=self.is_set,source_format=source)
            # Revalidate after each read: never open the second input or parse
            # selected bytes against an already superseded or held review.
            review=recheck_review()
            if right_path is not None:
                right_raw=read_selected_csv(right_path,halted=self.is_set(),halt_check=self.is_set)
                review=recheck_review()
        inputs=checked_sample_inputs(review,expected_scope,snapshot["context"],raw,right_raw=right_raw)
        bound=inputs.pop("max_cell_chars")
        contract=build_contract(snapshot,halted=self.is_set(),**inputs)
        left=_input(contract,raw,self.is_set(),self.is_set)
        right=_right_input(contract,right_raw,self.is_set(),self.is_set)
        for rows in (left,right or {}):
            for values in rows.values():
                if self.is_set():
                    raise PermissionError("deliverable withheld after halt")
                if any(len(value)>bound for value in values):
                    raise DeliverableError("DECLARED_CELL_BOUND_EXCEEDED")
        result=self._csv_scoped(plan_id,raw,snapshot=snapshot,right_raw=right_raw,**inputs)
        # A stable historical scope alone does not validate the full current
        # envelope; reject invalid digests or verification claims at return.
        recheck_review()
        return dict(review_scope_sha256=expected_scope,sample=result,external_authority=False)

    def csv_file_action(self,action,plan_id,*,confirmed=None,**inputs):
        """Fixed local preview/export actions; no arbitrary callback or external dispatch."""
        self._csv_ready(confirmed)
        fields={"preview":{"source_path","columns","key_column","expected_rows"},
                "export":{"source_path","columns","key_column","expected_rows",
                          "destination_path","expected_contract","expected_report","expected_artifact"},
                "register":{"source_path","columns","key_column","expected_rows",
                            "artifact_path","expected_contract","expected_report","expected_artifact"}}
        source_format=inputs.get("source_format","UTF8_CSV")
        operation=inputs.get("operation","PRESERVE")
        if type(action) is not str or action not in fields:
            raise ValueError("unsupported CSV action or inputs")
        required=fields[action]|({"right_source_path","right_expected_rows"} if operation=="RECONCILE" else set())
        if not (required<=set(inputs)<=(required|{"source_format","operation"})):
            raise ValueError("unsupported CSV action or inputs")
        from .digital_deliverable import build_contract
        from .deliverable_files import read_selected_csv, publish_new_csv, preview_pins
        from .checklist_store import _hash
        from hashlib import sha256
        self._operator_active=True
        try:
            snapshot=self._csv_snapshot(plan_id)
            if action in ("export","register"):
                for key in ("expected_contract","expected_report","expected_artifact"):
                    _hash(inputs[key])
            # Validate the declared schema and current source before file I/O.
            spec=dict(input_sha256="0"*64,columns=inputs["columns"],
                      key_column=inputs["key_column"],expected_rows=inputs["expected_rows"])
            if operation=="RECONCILE":
                spec.update(right_input_sha256="0"*64,right_expected_rows=inputs["right_expected_rows"])
            build_contract(snapshot,spec,halted=self.is_set(),source_format=source_format,operation=operation)
            raw=read_selected_csv(inputs["source_path"],halted=self.is_set(),halt_check=self.is_set,source_format=source_format)
            spec["input_sha256"]=sha256(raw).hexdigest()
            right_raw=None
            if operation=="RECONCILE":
                right_raw=read_selected_csv(inputs["right_source_path"],halted=self.is_set(),halt_check=self.is_set)
                spec["right_input_sha256"]=sha256(right_raw).hexdigest()
            result=self._csv_scoped(plan_id,raw,spec,snapshot=snapshot,source_format=source_format,operation=operation,right_raw=right_raw)
            if action=="preview":
                return result
            pins=preview_pins(result)
            if any(pins[key]!=inputs[key] for key in pins):
                raise ValueError("CSV preview changed; preview again before export")
            if action=="register":
                from .deliverable_obligations import ObligationStore, artifact_reference
                from .evidence import verify_reference
                match=verify_reference(inputs["artifact_path"],artifact_reference(result),
                                       halted=self.is_set(),halt_check=self.is_set)
                if match["byte_match"] is not True:
                    raise ValueError("selected artifact does not match reviewed deliverable")
                current=self._csv_snapshot(plan_id)
                if build_contract(current,spec,halted=self.is_set(),source_format=source_format,operation=operation)!=result["contract"]:
                    raise ValueError("deliverable scenario scope changed")
                path=self._directory/"operator-obligations.sqlite3"
                with ObligationStore(path,existing_only=os.path.lexists(path)) as store:
                    return store.register(result,now=self._clock(),confirmed=True,
                                          halted=self.is_set(),halt_check=self.is_set)
            publish_new_csv(inputs["destination_path"],result["artifact"],
                            halted=self.is_set(),halt_check=self.is_set)
            if self.is_set():
                raise PermissionError("halt after publication; inspect selected destination")
            return dict(pins,exported=True,report=result["report"],
                        buyer_accepted=False,external_authority=False)
        finally:
            self._operator_active=False

    def csv_obligation_action(self,action,plan_id,*,confirmed=None,**inputs):
        """Historical obligation review and evidence notes, not current buyer acceptance."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Operator unavailable while halted or faulted")
        fields={"history":{"obligation_id"},"list":{"limit"},
                "note":{"obligation_id","expected_head","kind","evidence_path"}}
        if type(action) is not str or action not in fields or set(inputs)!=fields[action]:
            raise ValueError("unsupported obligation action or inputs")
        from .deliverable_obligations import ObligationStore, NOTE_KINDS
        from .checklist_store import _hash
        _hash(plan_id)
        self._operator_active=True
        try:
            path=self._directory/"operator-obligations.sqlite3"
            if action=="list" and not os.path.lexists(path):
                return ObligationStore.empty_list(plan_id,inputs["limit"])
            if not os.path.lexists(path):
                raise ValueError("obligation history unavailable")
            with ObligationStore(path,existing_only=True) as store:
                kwargs=dict(now=self._clock(),halted=self.is_set(),halt_check=self.is_set)
                if action=="list":
                    return store.list_plan(plan_id,limit=inputs["limit"],**kwargs)
                record=store.history(plan_id,inputs["obligation_id"],**kwargs)
                if action=="history":
                    return record
                if confirmed is not True:
                    raise PermissionError("explicit historical evidence note confirmation required")
                _hash(inputs["expected_head"])
                if (inputs["expected_head"]!=record["head_sha256"] or
                        type(inputs["kind"]) is not str or inputs["kind"] not in NOTE_KINDS):
                    raise ValueError("obligation head or note kind mismatch")
                from .evidence import fingerprint
                reference=fingerprint(inputs["evidence_path"],halted=self.is_set(),halt_check=self.is_set)
                return store.note(plan_id,inputs["obligation_id"],kind=inputs["kind"],
                    expected_head=inputs["expected_head"],reference=reference,
                    now=self._clock(),confirmed=True,halted=self.is_set(),halt_check=self.is_set)
        finally:
            self._operator_active=False

    def simulated_invoice_action(self,action,plan_id,*,confirmed=None,**inputs):
        """Fixed local receivables simulation, never a real invoice or payment."""
        self._require_idle()
        if self._faulted or self.is_set():
            raise PermissionError("Operator unavailable while halted or faulted")
        fields={"preview":{"obligation_id","expected_obligation_head","issue_date"},
                "create":{"obligation_id","expected_obligation_head","issue_date","expected_invoice_id"},
                "history":{"invoice_id"},
                "find":set(),
                "cashflow":{"invoice_id","expected_head","expected_obligation_head","as_of","reserve_bps"},
                "payment":{"invoice_id","expected_head","sim_reference","amount","paid_on"}}
        if type(action) is not str or action not in fields or set(inputs)!=fields[action]:
            raise ValueError("unsupported simulated invoice action or inputs")
        from .checklist_store import _hash
        from .simulated_receivables import InvoiceStore, build_invoice
        from .deliverable_obligations import ObligationStore
        from .scenario_store import ScenarioStore
        _hash(plan_id)
        if action in ("create","payment") and confirmed is not True:
            raise PermissionError("explicit local simulation confirmation required")
        self._operator_active=True
        try:
            path=self._directory/"operator-simulated-invoices.sqlite3"
            obligations=self._directory/"operator-obligations.sqlite3"
            def opts():
                return dict(now=self._clock(),halted=self.is_set(),halt_check=self.is_set)
            def obligation(key):
                with ObligationStore(obligations,existing_only=True) as store:
                    return store.history(plan_id,key,**opts())
            if action in ("preview","create"):
                record=obligation(inputs["obligation_id"])
                if record["head_sha256"]!=_hash(inputs["expected_obligation_head"]):
                    raise ValueError("obligation changed; inspect current evidence")
                with ScenarioStore(self._directory/"scout-leads.sqlite3") as store:
                    saved=store.get(plan_id,halted=self.is_set())
                invoice=build_invoice(record,saved,issue_date=inputs["issue_date"],**opts())
                if action=="preview":
                    return invoice
                if invoice["invoice_id"]!=_hash(inputs["expected_invoice_id"]):
                    raise ValueError("invoice simulation preview changed")
                if obligation(record["obligation_id"])!=record:
                    raise ValueError("obligation changed before invoice creation")
                with InvoiceStore(path,existing_only=os.path.lexists(path)) as store:
                    return store.create(invoice,confirmed=True,**opts())
            if action=="find" and not os.path.lexists(path):
                return None
            with InvoiceStore(path,existing_only=True) as store:
                if action=="find":
                    return store.find(plan_id,**opts())
                record=store.history(plan_id,inputs["invoice_id"],**opts())
                if action=="history":
                    return record
                invoice=record["invoice"]
                if action=="cashflow":
                    from .cashflow_projection import project_cashflow
                    if record["head_sha256"]!=_hash(inputs["expected_head"]):
                        raise ValueError("simulation receipt history changed; refresh")
                    current=obligation(invoice["obligation_id"])
                    if current["head_sha256"]!=_hash(inputs["expected_obligation_head"]):
                        raise ValueError("obligation evidence changed; reopen from refreshed history")
                    with ScenarioStore(self._directory/"scout-leads.sqlite3") as scenarios:
                        saved=scenarios.get(plan_id,halted=self.is_set())
                    result=project_cashflow(record,current,saved,as_of=inputs["as_of"],
                        reserve_bps=inputs["reserve_bps"],halted=self.is_set(),halt_check=self.is_set)
                    if (obligation(invoice["obligation_id"])!=current or
                            store.history(plan_id,inputs["invoice_id"],**opts())!=record or self.is_set()):
                        raise ValueError("modeled cash-flow scope changed; refresh")
                    return result
                if obligation(invoice["obligation_id"])["head_sha256"]!=invoice["obligation_head_sha256"]:
                    raise ValueError("obligation evidence changed; simulation held for review")
                return store.payment(plan_id,inputs["invoice_id"],
                    expected_head=inputs["expected_head"],sim_reference=inputs["sim_reference"],
                    amount=inputs["amount"],paid_on=inputs["paid_on"],confirmed=True,**opts())
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
            """SELECT CASE WHEN typeof(slot)='integer' AND slot=1 THEN 1 END,
            CASE WHEN typeof(state)='text' AND length(CAST(state AS BLOB)) BETWEEN 1 AND 13
                 THEN CAST(state AS BLOB) END,
            CASE WHEN typeof(reason)='text' AND length(CAST(reason AS BLOB)) BETWEEN 1 AND 15
                 THEN CAST(reason AS BLOB) END,
            CASE WHEN typeof(revision)='integer' THEN revision END,
            CASE WHEN typeof(changed_at)='text' AND length(CAST(changed_at AS BLOB))=32
                 THEN CAST(changed_at AS BLOB) END
            FROM runtime_guard_v1 LIMIT 2""").fetchall()
        if not rows:
            return None
        if len(rows)!=1:
            raise ValueError("invalid runtime state cardinality")
        slot,state,reason,revision,stamp=rows[0]
        if any(type(value) is not bytes for value in (state,reason,stamp)):
            raise ValueError("invalid persisted runtime state")
        try:
            state,reason,stamp=(value.decode("ascii") for value in (state,reason,stamp))
        except UnicodeDecodeError:
            raise ValueError("invalid persisted runtime state") from None
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
            council_escalated_count=self.council_escalated_count,
            advisory_recovered_count=self.advisory_recovered_count,
            advisory_escalated_count=self.advisory_escalated_count,
            advisory_cleanup_unconfirmed=launch_marker.pending(self.events.db),external_authority=False)

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
            result=db.execute("""INSERT INTO runtime_guard_v1 VALUES (1,?,?,?,?)
                ON CONFLICT(slot) DO UPDATE SET state=excluded.state,reason=excluded.reason,
                revision=excluded.revision,changed_at=excluded.changed_at""",
                (state,reason,revision,stamp))
            expected=dict(state=state,reason=reason,revision=revision,changed_at=stamp)
            if result.rowcount!=1 or self._read()!=expected:
                raise ValueError("runtime state not persisted")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise

    def set(self):
        # Cooperative cancellation must precede disk operations.
        self._stop.set()
        self._require_owner()
        self._advisory_preview=None
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
            if launch_marker.pending(self.events.db):
                raise PermissionError("advisory process cleanup unconfirmed; quarantine retained")
            if self._advisory_pending():
                raise PermissionError("unfinished advisory reservations require halted recovery")
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
        if self._council_active or self._operator_active or self._browser_active or self._advisory_active:
            raise PermissionError("Local Council, Operator, Scout or advisory action must drain before close")
        self._stop.set()
        try:
            self._persist("halted","shutdown")
        finally:
            self._closed=True
            try:
                self.events.close()
            finally:
                self._lock.close()
