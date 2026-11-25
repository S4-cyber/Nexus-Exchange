import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from desktop import run_logged
from nexus_exchange.dashboard_events import project
from nexus_exchange.event_store import EventStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.governor import Action, decide

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)

def event(task,state,stamp=NOW):
    return dict(task_id=task,target="synthetic task",state=state,timestamp=stamp.isoformat())

class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.now=NOW

    def guard(self):
        return RuntimeGuard(self.directory,clock=lambda:self.now)

    def test_new_session_halted_and_resume_is_local_only(self):
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["state"],"halted")
            self.assertEqual(guard.status()["reason"],"startup")
            guard.resume()
            self.assertFalse(guard.is_set())
            self.assertTrue(decide(Action.RESEARCH_LOCAL,halted=guard.is_set()).allowed)
            for action in (Action.OUTREACH,Action.BID,Action.SIGNATURE,Action.PAYMENT):
                self.assertFalse(decide(action,halted=guard.is_set()).allowed)
            self.assertFalse(guard.status()["external_authority"])

    def test_halt_persists_and_reopen_requires_explicit_resume(self):
        with self.guard() as guard:
            guard.resume()
            guard.set()
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["reason"],"emergency")
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            guard.resume()
            self.assertFalse(guard.is_set())

    def test_exclusive_process_lock(self):
        script=("from nexus_exchange.runtime_guard import RuntimeGuard; import sys; "
                "g=RuntimeGuard(sys.argv[1]); g.close()")
        with self.guard():
            result=subprocess.run([sys.executable,"-c",script,str(self.directory)],
                                  capture_output=True,timeout=15)
            self.assertNotEqual(result.returncode,0)
        result=subprocess.run([sys.executable,"-c",script,str(self.directory)],
                              capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))

    def test_crash_recovery_no_replay(self):
        script=("from nexus_exchange.runtime_guard import RuntimeGuard; import sys,os; "
                "from datetime import datetime,timezone; "
                "n=datetime(2026,11,24,12,tzinfo=timezone.utc); "
                "g=RuntimeGuard(sys.argv[1],clock=lambda:n); g.resume(); "
                "g.events.append(dict(task_id='crashed',target='synthetic task',state='queued',timestamp=n.isoformat())); "
                "g.events.append(dict(task_id='crashed',target='synthetic task',state='running',timestamp=n.isoformat())); "
                "os._exit(0)")
        result=subprocess.run([sys.executable,"-c",script,str(self.directory)],
                              capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.now+=timedelta(seconds=1)
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.recovered_count,1)
            view=project(guard.events.read())
            self.assertEqual(view["history"][-1].state,"interrupted")
            self.assertEqual(view["successful_tasks"],0)
            self.assertEqual(view["tasks"],())
            guard.resume()
            self.assertFalse(guard.is_set())
        with self.guard() as guard:
            self.assertEqual(guard.recovered_count,0)
            self.assertEqual(len(guard.events.read()),3)

    def test_recovery_handles_all_active_tasks_not_just_first_page(self):
        store=EventStore(self.directory/"events.sqlite3")
        try:
            for i in range(14):
                store.append(event(str(i),"queued"))
                if i%2:
                    store.append(event(str(i),"running"))
            store.append(event("done","queued"))
            store.append(event("done","running"))
            store.append(event("done","succeeded"))
        finally:
            store.close()
        with self.guard() as guard:
            self.assertEqual(guard.recovered_count,14)
            view=project(guard.events.read())
            self.assertEqual(view["tasks"],())
            self.assertEqual(view["successful_tasks"],1)
            self.assertEqual(sum(e.state=="interrupted" for e in view["history"]),14)

    def test_resume_refused_when_tasks_active(self):
        with self.guard() as guard:
            guard.events.append(event("a","queued"))
            with self.assertRaises(PermissionError):
                guard.resume()
            self.assertTrue(guard.is_set())
            guard.events.append(event("a","cancelled"))
            guard.resume()
            self.assertFalse(guard.is_set())

    def test_failed_persistence_never_clears_stop(self):
        with self.guard() as guard:
            guard.resume()
            with patch.object(guard,"_persist",side_effect=OSError("synthetic")):
                with self.assertRaises(OSError):
                    guard.set()
            self.assertTrue(guard.is_set())
            with self.assertRaises(PermissionError):
                guard.resume()

    def test_corrupt_state_fails_closed_and_releases_lock(self):
        with self.guard():
            pass
        store=EventStore(self.directory/"events.sqlite3")
        try:
            store.db.execute("UPDATE runtime_guard_v1 SET state='unsafe'")
        finally:
            store.close()
        with self.assertRaises(ValueError):
            self.guard()
        store=EventStore(self.directory/"events.sqlite3")
        try:
            store.db.execute("DELETE FROM runtime_guard_v1")
        finally:
            store.close()
        with self.guard() as guard:
            self.assertTrue(guard.is_set())

    def test_backward_clock_recovery_fails_without_mutating_history(self):
        store=EventStore(self.directory/"events.sqlite3")
        try:
            store.append(event("future","queued",NOW+timedelta(days=1)))
        finally:
            store.close()
        with self.assertRaises(ValueError):
            self.guard()
        store=EventStore(self.directory/"events.sqlite3")
        try:
            self.assertEqual(len(store.read()),1)
        finally:
            store.close()
        self.now+=timedelta(days=1)
        with self.guard() as guard:
            self.assertEqual(guard.recovered_count,1)

    def test_halted_worker_does_not_dispatch(self):
        with self.guard() as guard:
            with patch("desktop.demo") as work:
                self.assertEqual(run_logged(guard.events,guard),())
                work.assert_not_called()
            self.assertEqual([e["state"] for e in guard.events.read()],["queued","cancelled"])

    def test_recovery_transaction_rolls_back_on_insert_failure(self):
        import sqlite3
        store=EventStore(self.directory/"events.sqlite3")
        try:
            store.append(event("a","queued"))
            store.append(event("b","queued"))
            store.db.execute("""CREATE TRIGGER fail_recovery BEFORE INSERT ON events
                WHEN json_extract(NEW.payload,'$.state')='interrupted'
                AND json_extract(NEW.payload,'$.task_id')='b'
                BEGIN SELECT RAISE(ABORT,'synthetic'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                store.recover_interrupted(now=NOW)
            self.assertEqual(len(store.read()),2)
            self.assertFalse(store.db.in_transaction)
            store.db.execute("DROP TRIGGER fail_recovery")
            self.assertEqual(store.recover_interrupted(now=NOW),2)
            self.assertEqual(store.recover_interrupted(now=NOW),0)
        finally:
            store.close()
