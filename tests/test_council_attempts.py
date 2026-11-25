import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from nexus_exchange.agent_handoff import parse_handoff
from nexus_exchange.council_attempts import CouncilAttemptStore

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
REPORT="a"*64

def handoff(attempt=1,**changes):
    raw=dict(task_id="TASK.1",from_role="Scout",to_role="Council",
        objective="Review synthetic commercial evidence",
        acceptance_criteria=["identity","source"],source_references=["synthetic source"],
        constraints=["offline only"],attempt=attempt)
    raw.update(changes)
    return parse_handoff(raw)

class CouncilAttemptTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"council.sqlite3"
        self.now=NOW

    def register(self,store,h=None,**kw):
        opts=dict(now=self.now,halted=False)
        opts.update(kw)
        return store.register(handoff() if h is None else h,**opts)

    def reserve(self,store,n=1,h=None,**kw):
        opts=dict(now=self.now,halted=False)
        opts.update(kw)
        return store.reserve(handoff(n) if h is None else h,**opts)

    def finish(self,store,ticket,status="RETRY",digest=REPORT,**kw):
        opts=dict(now=self.now,halted=False)
        opts.update(kw)
        return store.complete(ticket,status,digest,**opts)

    def recover(self,store,**kw):
        opts=dict(now=self.now,halted=False,exclusive_owner=True)
        opts.update(kw)
        return store.recover_interrupted("TASK.1",**opts)

    def test_registration_requires_first_attempt_and_trusted_identity(self):
        with CouncilAttemptStore(self.path) as store:
            with self.assertRaises(ValueError):
                self.register(store,handoff(2))
            with self.assertRaises(ValueError):
                self.reserve(store)
            state=self.register(store)
            self.assertEqual(state["next_attempt"],1)
            self.assertEqual(state["state"],"READY")
            self.assertEqual(self.register(store),state)
            with self.assertRaises(ValueError):
                self.register(store,handoff(objective="changed"))
            self.assertFalse(state["external_authority"])

    def test_third_failure_escalates_and_restart_cannot_reset(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            for n in range(1,4):
                ticket=self.reserve(store,n)
                state=self.finish(store,ticket,"NEEDS_EVIDENCE")
                self.assertEqual(state["attempts_used"],n)
                self.assertEqual(state["state"],"ESCALATE" if n==3 else "NEEDS_EVIDENCE")
        with CouncilAttemptStore(self.path) as store:
            state=store.status("TASK.1",halted=False)
            self.assertEqual(state["state"],"ESCALATE")
            self.assertIsNone(state["next_attempt"])
            self.assertEqual(self.register(store)["attempts_used"],3)
            with self.assertRaises(PermissionError):
                self.reserve(store,1)
            self.assertFalse(state["execution_eligible"])

    def test_reserved_attempt_cannot_dispatch_twice(self):
        with CouncilAttemptStore(self.path) as first,CouncilAttemptStore(self.path) as second:
            self.register(first)
            ticket=self.reserve(first)
            self.assertEqual(ticket["attempt"],1)
            for n in (1,2):
                with self.assertRaises(PermissionError):
                    self.reserve(second,n)
            state=self.finish(second,ticket)
            self.assertEqual(state["next_attempt"],2)
            with self.assertRaises(PermissionError):
                self.reserve(first,1)

    def test_out_of_order_and_changed_handoff_rejected(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            with self.assertRaises(PermissionError):
                self.reserve(store,2)
            with self.assertRaises(ValueError):
                self.reserve(store,h=handoff(objective="other"))
            self.assertEqual(store.status("TASK.1",halted=False)["attempts_used"],0)

    def test_success_is_review_only_and_terminal(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            ticket=self.reserve(store)
            result=self.finish(store,ticket,"ADVANCE_REVIEW_ONLY")
            self.assertEqual(result["state"],"ADVANCE_REVIEW_ONLY")
            for flag in ("external_authority","execution_eligible","commercial_facts_verified","release_eligible"):
                self.assertIs(result[flag],False)
            with self.assertRaises(PermissionError):
                self.reserve(store,2)

    def test_completion_replay_is_idempotent_and_conflicts_rejected(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            ticket=self.reserve(store)
            result=self.finish(store,ticket)
            self.now+=timedelta(seconds=1)
            self.assertEqual(self.finish(store,ticket),result)
            with self.assertRaises(ValueError):
                self.finish(store,ticket,"ADVANCE_REVIEW_ONLY")
            with self.assertRaises(ValueError):
                self.finish(store,dict(ticket,reservation_id="b"*64))

    def test_crash_consumes_attempt_and_never_replays(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            first=self.reserve(store)
        with CouncilAttemptStore(self.path) as store:
            self.assertEqual(store.status("TASK.1",halted=False)["state"],"RESERVED")
            with self.assertRaises(PermissionError):
                self.reserve(store,1)
            with self.assertRaises(PermissionError):
                self.recover(store,exclusive_owner=False)
            state=self.recover(store)
            self.assertEqual(state["state"],"INTERRUPTED")
            self.assertEqual(state["next_attempt"],2)
            self.assertEqual(self.recover(store),state)
            with self.assertRaises(ValueError):
                self.finish(store,first)
            self.reserve(store,2)
            self.recover(store)
            self.reserve(store,3)
            state=self.recover(store)
            self.assertEqual(state["state"],"ESCALATE")
            self.assertIsNone(state["next_attempt"])

    def test_halt_and_unknown_state_block_every_operation(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            ticket=self.reserve(store)
            for halted in (True,None,0):
                for action in (lambda:self.register(store,halted=halted),
                               lambda:self.reserve(store,halted=halted),
                               lambda:self.finish(store,ticket,halted=halted),
                               lambda:self.recover(store,halted=halted),
                               lambda:store.status("TASK.1",halted=halted)):
                    with self.assertRaises(PermissionError):
                        action()
            self.assertEqual(store.status("TASK.1",halted=False)["state"],"RESERVED")

    def test_bad_completion_fields_never_change_state(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            ticket=self.reserve(store)
            for status,digest in (("PASS",REPORT),("RETRY","é"*64),("RETRY",None),(True,REPORT)):
                with self.assertRaises(ValueError):
                    self.finish(store,ticket,status,digest)
            self.assertEqual(store.status("TASK.1",halted=False)["state"],"RESERVED")

    def test_backward_clock_and_transaction_rollback(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            self.now-=timedelta(seconds=1)
            with self.assertRaises(ValueError):
                self.reserve(store)
            self.now=NOW
            store.db.execute("""CREATE TRIGGER synthetic_failure BEFORE UPDATE ON council_attempts_v1
                BEGIN SELECT RAISE(ABORT,'synthetic'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                self.reserve(store)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(store.status("TASK.1",halted=False)["attempts_used"],0)
            store.db.execute("DROP TRIGGER synthetic_failure")
            self.reserve(store)

    def test_corruption_and_bounded_capacity(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            with patch("nexus_exchange.council_attempts.MAX_TASKS",1):
                self.register(store)
                with self.assertRaisesRegex(ValueError,"capacity"):
                    self.register(store,handoff(task_id="TASK.2"))
            store.db.execute("UPDATE council_attempts_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.status("TASK.1",halted=False)
            with self.assertRaises(ValueError):
                self.reserve(store)

    def test_no_raw_agent_text_or_artifacts_persisted(self):
        with CouncilAttemptStore(self.path) as store:
            self.register(store)
            ticket=self.reserve(store)
            self.finish(store,ticket)
            payload=store.db.execute("SELECT payload FROM council_attempts_v1").fetchone()[0]
            for secret in ("Review synthetic commercial evidence","synthetic source","offline only"):
                self.assertNotIn(secret,payload)
            self.assertIn(REPORT,payload)
