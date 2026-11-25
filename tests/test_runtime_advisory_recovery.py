import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore, DB_NAME
from nexus_exchange.runtime_guard import RuntimeGuard
from test_context_packet import snapshot, PLAN, NOW
from test_local_advisory_integration import MODEL


class RuntimeAdvisoryTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name)
        self.path=self.directory/DB_NAME
        self.now=NOW

    def guard(self):
        return RuntimeGuard(self.directory,clock=lambda:self.now)

    def reserve(self,store):
        return store.reserve(snapshot(),MODEL,now=self.now,approved=True,halted=False)

    def test_startup_and_resume_do_not_create_absent_database(self):
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["advisory_recovered_count"],0)
            guard.resume()
        self.assertFalse(self.path.exists())

    def test_startup_consumes_third_reservation_without_resuming(self):
        with AdvisoryAttemptStore(self.path) as store:
            for _ in range(2):
                r=self.reserve(store)
                store.fail(r["ticket"],"WORKER_FAILED",now=self.now,approved=True,
                           halted=False,worker_drained=True)
            self.reserve(store)
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["advisory_recovered_count"],1)
            self.assertEqual(guard.status()["advisory_escalated_count"],1)
            with AdvisoryAttemptStore(self.path,existing_only=True) as store:
                status=store.status(PLAN,halted=False)
                self.assertEqual(status["state"],"ESCALATED")
                self.assertEqual(status["attempts_used"],3)
                self.assertIsNone(status["next_attempt"])
            guard.resume()
            self.assertFalse(guard.is_set())
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.advisory_recovered_count,0)

    def test_same_session_recovery_denies_running_busy_and_wrong_thread(self):
        with self.guard() as guard:
            guard.resume()
            with AdvisoryAttemptStore(self.path) as store:
                self.reserve(store)
            with self.assertRaises(PermissionError):
                guard.recover_advisory()
            guard.set()
            with self.assertRaises(PermissionError):
                guard.resume()
            guard.events.append(dict(task_id="worker",target="Synthetic",state="queued",
                                     timestamp=self.now.isoformat()))
            with self.assertRaises(PermissionError):
                guard.recover_advisory()
            guard.events.append(dict(task_id="worker",target="Synthetic",state="cancelled",
                                     timestamp=self.now.isoformat()))
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(PermissionError):
                    pool.submit(guard.recover_advisory).result(timeout=5)
            self.assertEqual(guard.recover_advisory(),dict(recovered=1,escalated=0))
            self.assertTrue(guard.is_set())
            guard.resume()
            self.assertFalse(guard.is_set())
            with AdvisoryAttemptStore(self.path,existing_only=True) as store:
                self.assertEqual(self.reserve(store)["ticket"]["attempt"],2)

    def test_corrupt_ledger_blocks_startup_and_releases_directory_lock(self):
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            row=store.db.execute("SELECT payload,digest FROM advisory_attempts_v1").fetchone()
            store.db.execute("UPDATE advisory_attempts_v1 SET payload='{}'")
        with self.assertRaises(ValueError):
            self.guard()
        with AdvisoryAttemptStore(self.path,existing_only=True) as store:
            store.db.execute("UPDATE advisory_attempts_v1 SET payload=?,digest=?",row)
        with self.guard() as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.advisory_recovered_count,1)

    def test_corruption_after_startup_keeps_runtime_halted(self):
        with self.guard() as guard:
            guard.resume()
            with AdvisoryAttemptStore(self.path) as store:
                self.reserve(store)
                store.db.execute("UPDATE advisory_attempts_v1 SET payload='{}'")
            guard.set()
            with self.assertRaises(ValueError):
                guard.resume()
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.status()["reason"],"persistence_fault")
            with self.assertRaises(PermissionError):
                guard.resume()


if __name__=="__main__":
    unittest.main()
