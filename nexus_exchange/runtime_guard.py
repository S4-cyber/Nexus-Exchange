"""Exclusive, fail-closed local desktop session and durable halt state.

Only the desktop owner invokes resume; worker threads observe a cooperative
threading.Event. The OS lock is held until workers have drained and close
returns. No external authorization or automatic task replay.
"""
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
        if self._council_active or project(self.events.read())["tasks"]:
            raise PermissionError("active worker must drain before Council maintenance")

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
        if self._council_active:
            raise PermissionError("Council action must drain before close")
        self._stop.set()
        try:
            self._persist("halted","shutdown")
        finally:
            self._closed=True
            try:
                self.events.close()
            finally:
                self._lock.close()
