import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange.council_attempts import CouncilAttemptStore
from nexus_exchange.council_criterion_review import CriterionSpec, MAX_ARTIFACT_BYTES
from nexus_exchange.council_coordinator import CouncilCoordinator, build_task
from nexus_exchange.lead_store import _digest, _json

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
SCOPE="a"*64
POLICY="b"*64

def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"council.sqlite3"
        self.now=NOW
        self.halted=False
        self.artifacts={"identity":b"synthetic identity","source":b"synthetic source"}
        self.checks={k:Mock(return_value=True) for k in self.artifacts}
        self.specs=tuple(CriterionSpec(k,digest(v),self.checks[k]) for k,v in self.artifacts.items())
        self.task=build_task(SCOPE,POLICY,self.specs)

    def coordinator(self,store):
        return CouncilCoordinator(store,halt_check=lambda:self.halted,clock=lambda:self.now)

    def test_registration_and_one_review_only(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            with self.assertRaises(ValueError):
                coordinator.run_once(self.task,self.artifacts)
            state=coordinator.register(self.task)
            self.assertEqual(state["task_id"],"COUNCIL."+SCOPE)
            self.assertEqual(state["next_attempt"],1)
            result=coordinator.run_once(self.task,self.artifacts)
            self.assertEqual(result["review"]["status"],"ADVANCE_REVIEW_ONLY")
            self.assertEqual(result["ledger"]["state"],"ADVANCE_REVIEW_ONLY")
            self.assertTrue(result["durable_retry_enforced"])
            self.assertEqual(result["report_sha256"],_digest(_json(result["review"])))
            self.assertEqual(result["ledger"]["attempts"][0]["report_sha256"],result["report_sha256"])
            for flag in ("external_authority","execution_eligible","commercial_facts_verified","release_eligible"):
                self.assertIs(result[flag],False)
            for key,check in self.checks.items():
                check.assert_called_once_with(self.artifacts[key])
            with self.assertRaises(PermissionError):
                coordinator.run_once(self.task,self.artifacts)
            payload=store.db.execute("SELECT payload FROM council_attempts_v1").fetchone()[0]
            self.assertNotIn("synthetic identity",payload)

    def test_three_missing_attempts_across_reopen(self):
        for attempt in range(1,4):
            with CouncilAttemptStore(self.path) as store:
                coordinator=self.coordinator(store)
                self.assertEqual(coordinator.register(self.task)["attempts_used"],attempt-1)
                result=coordinator.run_once(self.task,{})
                self.assertEqual(result["review"]["attempt"],attempt)
                self.assertEqual(result["ledger"]["state"],"ESCALATE" if attempt==3 else "NEEDS_EVIDENCE")
            self.now+=timedelta(seconds=1)
        with CouncilAttemptStore(self.path) as store:
            with self.assertRaises(PermissionError):
                self.coordinator(store).run_once(self.task,self.artifacts)
        for check in self.checks.values():
            check.assert_not_called()

    def test_changed_pins_or_policy_cannot_reset_scope(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            coordinator.run_once(self.task,{})
            changed=build_task(SCOPE,"c"*64,self.specs)
            pins=(replace(self.specs[0],expected_sha256=digest(b"different")),self.specs[1])
            for task in (changed,build_task(SCOPE,POLICY,pins),build_task(SCOPE,POLICY,self.specs[::-1])):
                with self.assertRaises(ValueError):
                    coordinator.register(task)
                with self.assertRaises(ValueError):
                    coordinator.run_once(task,self.artifacts)
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["attempts_used"],1)
            other=build_task("d"*64,POLICY,self.specs)
            self.assertEqual(coordinator.register(other)["attempts_used"],0)

    def test_malformed_inputs_do_not_consume_attempt(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            for bad in ({"identity":"PASS"},{"identity":b""},{"unknown":b"x"},
                        {"identity":b"x"*(MAX_ARTIFACT_BYTES+1)}):
                with self.assertRaises(ValueError):
                    coordinator.run_once(self.task,bad)
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["attempts_used"],0)
            for check in self.checks.values():
                check.assert_not_called()

    def test_halt_before_reservation_and_during_check(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            for state in (True,None,0):
                self.halted=state
                with self.assertRaises(PermissionError):
                    coordinator.run_once(self.task,self.artifacts)
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["attempts_used"],0)
            self.halted=False
            def halt(_):
                self.halted=True
                return True
            self.checks["identity"].side_effect=halt
            with self.assertRaises(PermissionError):
                coordinator.run_once(self.task,self.artifacts)
            self.checks["source"].assert_not_called()
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["state"],"RESERVED")
        with CouncilAttemptStore(self.path) as store:
            self.halted=False
            coordinator=self.coordinator(store)
            with self.assertRaises(PermissionError):
                coordinator.run_once(self.task,self.artifacts)
            state=store.recover_interrupted("COUNCIL."+SCOPE,now=NOW,exclusive_owner=True,halted=False)
            self.assertEqual(state["next_attempt"],2)
            self.checks["identity"].side_effect=None
            self.assertEqual(coordinator.run_once(self.task,self.artifacts)["review"]["attempt"],2)

    def test_reservation_exists_before_trusted_check(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            def inspect(_):
                with CouncilAttemptStore(self.path) as observer:
                    state=observer.status("COUNCIL."+SCOPE,halted=False)
                    self.assertEqual(state["state"],"RESERVED")
                    self.assertEqual(state["attempts_used"],1)
                return True
            self.checks["identity"].side_effect=inspect
            self.assertEqual(coordinator.run_once(self.task,self.artifacts)["ledger"]["state"],"ADVANCE_REVIEW_ONLY")

    def test_completion_error_never_automatically_replays(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            with patch.object(store,"complete",side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    coordinator.run_once(self.task,self.artifacts)
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["state"],"RESERVED")
            with self.assertRaises(PermissionError):
                coordinator.run_once(self.task,self.artifacts)
            self.checks["identity"].assert_called_once()

    def test_reject_invalid_task_or_halt_checker(self):
        for scope,policy,specs in (("é"*64,POLICY,self.specs),(SCOPE,True,self.specs),
            (SCOPE,POLICY,()),(SCOPE,POLICY,self.specs+(self.specs[0],)),
            (SCOPE,POLICY,(replace(self.specs[0],expected_sha256="x"*64),))):
            with self.assertRaises(ValueError):
                build_task(scope,policy,specs)
        with CouncilAttemptStore(self.path) as store:
            with self.assertRaises(ValueError):
                CouncilCoordinator(store,halt_check=None)
            coordinator=self.coordinator(store)
            with self.assertRaises(ValueError):
                coordinator.register(replace(self.task,scope_sha256="invalid"))
            self.halted=True
            with self.assertRaises(PermissionError):
                coordinator.register(self.task)

    def test_failed_predicate_cannot_claim_success(self):
        self.checks["identity"].return_value=False
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            result=coordinator.run_once(self.task,self.artifacts)
            self.assertEqual(result["ledger"]["state"],"RETRY")
            self.assertEqual(result["review"]["criteria"][0]["reason"],"CHECK_FAILED")
            self.assertFalse(result["commercial_facts_verified"])

    def test_future_or_wrong_report_rejected_before_completion(self):
        with CouncilAttemptStore(self.path) as store:
            coordinator=self.coordinator(store)
            coordinator.register(self.task)
            with patch("nexus_exchange.council_coordinator.review_criteria",return_value={
                "task_id":"wrong","attempt":1,"status":"ADVANCE_REVIEW_ONLY","external_authority":True}):
                with self.assertRaises(ValueError):
                    coordinator.run_once(self.task,self.artifacts)
            self.assertEqual(store.status("COUNCIL."+SCOPE,halted=False)["state"],"RESERVED")
