import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore, DB_NAME
from nexus_exchange.database_backup import create_backup, restore_backup
from nexus_exchange.runtime_guard import RuntimeGuard
from test_context_packet import snapshot, NOW, PLAN
from test_local_advisory_integration import wire, MODEL


class AdvisoryLedgerIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name).resolve()
        self.path=self.directory/DB_NAME

    def reserve(self,store,s,now=NOW,model=MODEL):
        return store.reserve(s,model,now=now,approved=True,halted=False)

    def finish(self,store,r,s,raw,now=NOW):
        return store.complete(r["ticket"],r["request"],s,raw,now=now,
                              approved=True,halted=False,worker_drained=True)

    def test_exact_council_review_persisted_as_digest_only(self):
        s=snapshot(held=True,reference=True)
        with AdvisoryAttemptStore(self.path) as store:
            r=self.reserve(store,s)
            field=r["request"]["fields"][0]
            raw=wire(r["request"],[dict(field=field["field"],reason=field["state"],
                                       reference_id=field["reference_ids"][0])])
            result=self.finish(store,r,s,raw)
            self.assertEqual(result["review"]["source_hold"],"SOURCE_REVIEW_REQUIRED")
            self.assertFalse(result["review"]["external_authority"])
            self.assertFalse(result["execution_eligible"])
            stored=store.db.execute("SELECT payload FROM advisory_attempts_v1").fetchone()[0]
            self.assertNotIn(field["reference_ids"][0],stored)
            self.assertIn(result["review"]["response_sha256"],stored)
        with AdvisoryAttemptStore(self.path,existing_only=True) as store:
            self.assertEqual(store.status(PLAN,halted=False)["state"],"REVIEWED")
            with self.assertRaises(PermissionError):
                self.reserve(store,s)

    def test_stale_response_and_third_interruption_escalate(self):
        s=snapshot()
        with AdvisoryAttemptStore(self.path) as store:
            for n in range(1,4):
                r=self.reserve(store,s)
                self.assertEqual(r["ticket"]["attempt"],n)
                with self.assertRaises(ValueError):
                    self.finish(store,r,s,wire(r["request"],[]),now=NOW+timedelta(minutes=6))
                self.assertEqual(store.status(PLAN,halted=False)["state"],"RESERVED")
                state=store.recover_interrupted(PLAN,now=NOW,halted=True,
                                                exclusive_owner=True,worker_drained=True)
            self.assertEqual(state["state"],"ESCALATED")
            with self.assertRaises(PermissionError):
                self.reserve(store,snapshot(held=True),model="f"*64)

    def test_closed_backup_retains_reserved_attempt_without_replay(self):
        source=self.directory/"source"
        backup=self.directory/"backup"
        dest=self.directory/"restored"
        s=snapshot()
        with RuntimeGuard(source,clock=lambda:NOW) as guard:
            guard.resume()
            with AdvisoryAttemptStore(source/DB_NAME) as store:
                self.reserve(store,s)
        manifest=create_backup(source,backup,confirmed=True)
        self.assertIn(DB_NAME,[row["name"] for row in manifest["files"]])
        restore_backup(backup,dest,confirmed=True)
        with RuntimeGuard(dest,clock=lambda:NOW) as guard:
            self.assertTrue(guard.is_set())
            with AdvisoryAttemptStore(dest/DB_NAME,existing_only=True) as store:
                state=store.recover_interrupted(PLAN,now=NOW,halted=guard.is_set(),
                                                exclusive_owner=True,worker_drained=True)
                self.assertEqual(state["state"],"INTERRUPTED")
                self.assertEqual(state["attempts_used"],1)
                guard.resume()
                self.assertEqual(self.reserve(store,s)["ticket"]["attempt"],2)


if __name__=="__main__":
    unittest.main()
