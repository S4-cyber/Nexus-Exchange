import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange.agent_handoff import parse_handoff
from nexus_exchange.council_attempts import CouncilAttemptStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.governor import Action, decide
from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_evidence import ScenarioEvidenceStore
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam


def handoff(task="TASK.1",attempt=1):
    return parse_handoff(dict(task_id=task,from_role="Scout",to_role="Council",
        objective="Synthetic offline review",acceptance_criteria=["source"],
        source_references=["synthetic"],constraints=["offline"],attempt=attempt))


class RuntimeCouncilTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.path=self.directory/"council.sqlite3"
        self.now=NOW

    def guard(self):
        return RuntimeGuard(self.directory,clock=lambda:self.now)

    def reserve(self,store,task="TASK.1",attempt=1):
        if attempt==1:
            store.register(handoff(task),now=self.now,halted=False)
        return store.reserve(handoff(task,attempt),now=self.now,halted=False)

    def test_missing_council_database_not_created_by_startup_resume(self):
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.council_recovered_count,0)
            self.assertEqual(guard.council_escalated_count,0)
            guard.resume()
            self.assertFalse(guard.is_set())
        self.assertFalse(self.path.exists())

    def test_startup_reconciles_all_reserved_tasks_without_replay(self):
        with CouncilAttemptStore(self.path) as store:
            for i in range(14):
                self.reserve(store,"TASK."+str(i))
            done=self.reserve(store,"DONE")
            store.complete(done,"ADVANCE_REVIEW_ONLY","a"*64,now=self.now,halted=False)
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.council_recovered_count,14)
            self.assertEqual(guard.council_escalated_count,0)
            with CouncilAttemptStore(self.path) as store:
                for i in range(14):
                    state=store.audit_history("TASK."+str(i),halted=False)
                    self.assertEqual(state["state"],"INTERRUPTED")
                    self.assertEqual(state["attempts_used"],1)
                    self.assertEqual(state["attempts"][0]["audit_state"],"INTERRUPTED_NO_REPORT")
                self.assertEqual(store.status("DONE",halted=False)["state"],"ADVANCE_REVIEW_ONLY")
            guard.resume()
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,0)
            self.assertTrue(guard.is_set())

    def test_third_interrupted_attempt_escalates_across_restart(self):
        with CouncilAttemptStore(self.path) as store:
            for n in range(1,4):
                ticket=self.reserve(store,attempt=n)
                if n<3:
                    store.complete(ticket,"NEEDS_EVIDENCE","a"*64,now=self.now,halted=False)
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,1)
            self.assertEqual(guard.council_escalated_count,1)
            guard.resume()
            with CouncilAttemptStore(self.path) as store:
                state=store.audit_history("TASK.1",halted=False)
                self.assertEqual(state["state"],"ESCALATE")
                self.assertEqual(state["attempts_used"],3)
                self.assertIsNone(state["next_attempt"])
                self.assertEqual(state["attempts"][-1]["audit_state"],"INTERRUPTED_NO_REPORT")
                with self.assertRaises(PermissionError):
                    self.reserve(store)

    def test_actual_subprocess_crash_consumes_reservation(self):
        script=("import os,sys; from pathlib import Path; from datetime import datetime,timezone; "
                "from nexus_exchange.runtime_guard import RuntimeGuard; "
                "from nexus_exchange.council_attempts import CouncilAttemptStore; "
                "from nexus_exchange.agent_handoff import parse_handoff; "
                "n=datetime.fromisoformat(sys.argv[2]); p=Path(sys.argv[1]); "
                "g=RuntimeGuard(p,clock=lambda:n); g.resume(); "
                "s=CouncilAttemptStore(p/'council.sqlite3'); "
                "h=parse_handoff(dict(task_id='CRASH',from_role='Scout',to_role='Council',"
                "objective='Synthetic',acceptance_criteria=['a'],source_references=['b'],"
                "constraints=['offline'],attempt=1)); "
                "s.register(h,now=n,halted=False); s.reserve(h,now=n,halted=False); os._exit(0)")
        result=subprocess.run([sys.executable,"-c",script,str(self.directory),self.now.isoformat()],
                              capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.now+=timedelta(seconds=1)
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,1)
            self.assertTrue(guard.is_set())
            with CouncilAttemptStore(self.path) as store:
                self.assertEqual(store.status("CRASH",halted=False)["state"],"INTERRUPTED")

    def test_resume_requires_explicit_recovery_for_same_session_reservation(self):
        with self.guard() as guard:
            guard.resume()
            with CouncilAttemptStore(self.path) as store:
                self.reserve(store)
            with self.assertRaises(PermissionError):
                guard.recover_council()
            guard.set()
            with self.assertRaises(PermissionError):
                guard.resume()
            self.assertTrue(guard.is_set())
            result=guard.recover_council()
            self.assertEqual(result,dict(recovered=1,escalated=0))
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.recover_council(),dict(recovered=0,escalated=0))
            guard.resume()
            self.assertFalse(guard.is_set())
            self.assertFalse(decide(Action.BID,halted=guard.is_set()).allowed)

    def test_active_worker_and_wrong_thread_cannot_recover(self):
        with self.guard() as guard:
            guard.resume()
            with CouncilAttemptStore(self.path) as store:
                self.reserve(store)
            guard.set()
            guard.events.append(dict(task_id="worker",target="Synthetic",state="queued",
                timestamp=self.now.isoformat()))
            with self.assertRaises(PermissionError):
                guard.recover_council()
            guard.events.append(dict(task_id="worker",target="Synthetic",state="cancelled",
                timestamp=self.now.isoformat()))
            with ThreadPoolExecutor(max_workers=1) as pool:
                for operation in (guard.recover_council,guard.resume):
                    with self.assertRaises(PermissionError):
                        pool.submit(operation).result(timeout=5)
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.recover_council()["recovered"],1)

    def test_recovery_rolls_back_all_tasks_on_later_write_failure(self):
        with CouncilAttemptStore(self.path) as store:
            self.reserve(store,"A")
            self.reserve(store,"B")
            store.db.execute("""CREATE TRIGGER reject_b BEFORE UPDATE ON council_attempts_v1
                WHEN OLD.task_id='B' BEGIN SELECT RAISE(ABORT,'synthetic'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.guard()
        with CouncilAttemptStore(self.path) as store:
            for task in ("A","B"):
                self.assertEqual(store.status(task,halted=False)["state"],"RESERVED")
            store.db.execute("DROP TRIGGER reject_b")
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,2)
            self.assertTrue(guard.is_set())

    def test_corrupt_ledger_and_missing_existing_schema_fail_closed(self):
        with CouncilAttemptStore(self.path) as store:
            self.reserve(store)
            original=store.db.execute("SELECT payload,digest FROM council_attempts_v1").fetchone()
            store.db.execute("UPDATE council_attempts_v1 SET payload='{}'")
        with self.assertRaises(ValueError):
            self.guard()
        with CouncilAttemptStore(self.path) as store:
            store.db.execute("UPDATE council_attempts_v1 SET payload=?,digest=?",original)
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,1)
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE council_attempts_v1")
        with self.assertRaises(ValueError):
            self.guard()

    def test_future_reservation_aborts_batch_recovery(self):
        with CouncilAttemptStore(self.path) as store:
            self.reserve(store,"A")
            self.now+=timedelta(days=1)
            self.reserve(store,"B")
        self.now-=timedelta(days=1)
        with self.assertRaises(ValueError):
            self.guard()
        with CouncilAttemptStore(self.path) as store:
            self.assertEqual(store.status("A",halted=False)["state"],"RESERVED")
            self.assertEqual(store.status("B",halted=False)["state"],"RESERVED")
        self.now+=timedelta(days=1)
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,2)

    def fixture(self):
        declared=profile()
        report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:self.now)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(declared,halted=False)
        with ScenarioEvidenceStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(report,now=self.now,halted=False)
            lead=store.browse(now=self.now,profile=declared,source="sam",halted=False)["leads"][0]
            return store.save(context_for(lead),scenario(),plan(),profile=declared,
                now=self.now,halted=False)

    def test_runtime_bound_scenario_review_and_historical_audit(self):
        key=self.fixture()
        with self.guard() as guard:
            for action in ("inspect","register","run_once","history"):
                with self.assertRaises(PermissionError):
                    guard.council_action(action,key)
            guard.resume()
            self.assertEqual(guard.council_action("inspect",key)["plan_id"],key)
            with self.assertRaises(ValueError):
                guard.council_action("complete",key)
            guard.council_action("register",key)
            result=guard.council_action("run_once",key)
            self.assertEqual(result["ledger"]["attempts_used"],1)
            self.assertFalse(result["external_authority"])
            history=guard.council_action("history",key)
            self.assertEqual(history["attempts"][0]["audit_state"],"RECORDED")
            guard.set()
            with self.assertRaises(PermissionError):
                guard.council_action("history",key)
        with self.guard() as guard:
            guard.resume()
            self.assertEqual(guard.council_action("history",key)["attempts_used"],1)
            self.assertEqual(guard.council_action("run_once",key)["ledger"]["attempts_used"],2)

    def test_guarded_council_dispatch_blocks_reentrant_and_thread_calls(self):
        key=self.fixture()
        with self.guard() as guard:
            guard.resume()
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(PermissionError):
                    pool.submit(guard.council_action,"inspect",key).result(timeout=5)
            from nexus_exchange.scenario_council import ScenarioCouncil
            original=ScenarioCouncil.inspect
            def reentrant(adapter,plan_id):
                with self.assertRaises(PermissionError):
                    guard.council_action("inspect",plan_id)
                with self.assertRaises(PermissionError):
                    guard.close()
                return original(adapter,plan_id)
            with patch.object(ScenarioCouncil,"inspect",reentrant):
                self.assertEqual(guard.council_action("inspect",key)["plan_id"],key)
        with self.assertRaises(PermissionError):
            guard.council_action("inspect",key)

    def test_halt_during_review_leaves_reservation_then_owner_recovers(self):
        key=self.fixture()
        with self.guard() as guard:
            guard.resume()
            state=guard.council_action("register",key)
            def interrupted(*args,**kwargs):
                guard.set()
                raise PermissionError("HALTED")
            with patch("nexus_exchange.council_coordinator.review_criteria",side_effect=interrupted):
                with self.assertRaises(PermissionError):
                    guard.council_action("run_once",key)
            self.assertTrue(guard.is_set())
            with self.assertRaises(PermissionError):
                guard.resume()
            self.assertEqual(guard.recover_council()["recovered"],1)
            guard.resume()
            result=guard.council_action("run_once",key)
            self.assertEqual(result["ledger"]["attempts_used"],2)
            history=guard.council_action("history",key)
            self.assertEqual([row["audit_state"] for row in history["attempts"]],
                             ["INTERRUPTED_NO_REPORT","RECORDED"])
            self.assertEqual(history["task_id"],state["task_id"])

    def test_unexpected_review_failure_asserts_halt_and_requires_recovery(self):
        key=self.fixture()
        with self.guard() as guard:
            guard.resume()
            guard.council_action("register",key)
            with patch("nexus_exchange.council_coordinator.review_criteria",side_effect=RuntimeError("synthetic")):
                with self.assertRaises(RuntimeError):
                    guard.council_action("run_once",key)
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["persisted_state"],"halted")
            with self.assertRaises(PermissionError):
                guard.resume()
            self.assertEqual(guard.recover_council()["recovered"],1)
            guard.resume()
            self.assertEqual(guard.council_action("run_once",key)["ledger"]["attempts_used"],2)

    def test_startup_preserves_prior_completed_v2_audit(self):
        from nexus_exchange.scenario_council import ScenarioCouncil
        from nexus_exchange.council_coordinator import _prepare
        key=self.fixture()
        with self.guard() as guard:
            guard.resume()
            guard.council_action("register",key)
            first=guard.council_action("run_once",key)
            adapter=ScenarioCouncil(self.directory,halt_check=guard.is_set,clock=lambda:self.now)
            with adapter._snapshot(key) as (_snapshot,task,_artifacts):
                h,_=_prepare(task,2)
                with CouncilAttemptStore(self.path) as store:
                    store.reserve(h,now=self.now,halted=False)
        self.now+=timedelta(seconds=1)
        with self.guard() as guard:
            self.assertEqual(guard.council_recovered_count,1)
            guard.resume()
            history=guard.council_action("history",key)
            self.assertEqual([row["audit_state"] for row in history["attempts"]],
                             ["RECORDED","INTERRUPTED_NO_REPORT"])
            self.assertEqual(history["attempts"][0]["report_sha256"],first["report_sha256"])
            self.assertEqual(history["attempts"][0]["audit"]["snapshot"]["snapshot_sha256"],
                             first["snapshot"]["snapshot_sha256"])

    def test_orphaned_audit_without_task_blocks_startup(self):
        with CouncilAttemptStore(self.path):
            pass
        db=sqlite3.connect(self.path)
        try:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("INSERT INTO council_review_audit_v1 VALUES ('missing',1,'{}','bad')")
            db.commit()
        finally:
            db.close()
        with self.assertRaises(ValueError):
            self.guard()
