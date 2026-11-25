import hashlib
import unittest
from dataclasses import replace
from unittest.mock import Mock

from nexus_exchange.agent_handoff import parse_handoff
from nexus_exchange.council_criterion_review import (
    CriterionSpec, build_review_plan, review_criteria, MAX_ARTIFACT_BYTES,
)


def handoff(attempt=1, **changes):
    return parse_handoff(dict(task_id="TASK.1",from_role="Scout",to_role="Council",
        objective="Review synthetic local evidence",acceptance_criteria=["identity","source"],
        source_references=["untrusted agent reference"],constraints=["offline only"],
        attempt=attempt) | changes)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class CouncilCriterionTests(unittest.TestCase):
    def setUp(self):
        self.h=handoff()
        self.artifacts={"identity":b"synthetic identity","source":b"synthetic source"}
        self.checks={key:Mock(return_value=True) for key in self.artifacts}
        self.specs=tuple(CriterionSpec(k,digest(v),self.checks[k]) for k,v in self.artifacts.items())

    def review(self,artifacts=None,*,h=None,plan=None,halted=False,halt_check=None):
        h=self.h if h is None else h
        if plan is None:
            plan=build_review_plan(h,self.specs)
        return review_criteria(h,plan,self.artifacts if artifacts is None else artifacts,
                               halted=halted,halt_check=halt_check)

    def test_exact_criteria_and_trusted_checks_required(self):
        result=self.review()
        self.assertEqual(result["status"],"ADVANCE_REVIEW_ONLY")
        self.assertEqual([x["criterion"] for x in result["criteria"]],["identity","source"])
        self.assertTrue(all(x["reason"]=="CHECK_PASSED" for x in result["criteria"]))
        for key,check in self.checks.items():
            check.assert_called_once_with(self.artifacts[key])
        self.assertIs(result["external_authority"],False)
        self.assertIs(result["execution_eligible"],False)
        self.assertIs(result["commercial_facts_verified"],False)
        self.assertIs(result["release_eligible"],False)
        self.assertNotIn("synthetic identity",str(result))

    def test_partial_and_missing_criteria(self):
        result=self.review({"identity":self.artifacts["identity"]})
        self.assertEqual(result["status"],"NEEDS_EVIDENCE")
        self.assertEqual(result["criteria"][1]["reason"],"MISSING_ARTIFACT")
        self.checks["source"].assert_not_called()
        with self.assertRaises(ValueError):
            build_review_plan(self.h,self.specs[:1])

    def test_digest_mismatch_skips_predicate(self):
        result=self.review(dict(self.artifacts,identity=b"replaced"))
        self.assertEqual(result["status"],"RETRY")
        self.assertEqual(result["criteria"][0]["reason"],"ARTIFACT_DIGEST_MISMATCH")
        self.checks["identity"].assert_not_called()

    def test_matching_bytes_do_not_replace_independent_check(self):
        for value in (False,None,1,"PASS"):
            self.checks["source"].return_value=value
            result=self.review()
            self.assertEqual(result["status"],"RETRY")
            self.assertEqual(result["criteria"][1]["reason"],"CHECK_FAILED")

    def test_check_exception_sanitized(self):
        self.checks["source"].side_effect=RuntimeError("private payload")
        result=self.review()
        self.assertEqual(result["criteria"][1]["reason"],"CHECK_ERROR")
        self.assertNotIn("private payload",str(result))

    def test_third_missing_or_failed_attempt_escalates(self):
        h=handoff(3)
        self.assertEqual(self.review({},h=h)["status"],"ESCALATE")
        self.checks["identity"].return_value=False
        self.assertEqual(self.review(h=h)["status"],"ESCALATE")
        self.checks["identity"].return_value=True
        self.assertEqual(self.review(h=h)["status"],"ADVANCE_REVIEW_ONLY")

    def test_plan_bound_to_exact_handoff_including_attempt(self):
        plan=build_review_plan(self.h,self.specs)
        for h in (handoff(2),handoff(objective="different"),handoff(task_id="TASK.2"),
                  handoff(acceptance_criteria=["source","identity"])):
            with self.assertRaises(ValueError):
                self.review(h=h,plan=plan)
        for check in self.checks.values():
            check.assert_not_called()

    def test_reject_untrusted_or_oversized_input_before_predicates(self):
        for raw in ({"identity":"PASS"}, {"identity":bytearray(b"x")},
                    {"identity":b"x","invented":b"x"},
                    {"identity":b"x"*(MAX_ARTIFACT_BYTES+1)}, {"identity":b""}):
            with self.assertRaises(ValueError):
                self.review(raw)
        for check in self.checks.values():
            check.assert_not_called()
        for specs in (self.specs+(self.specs[0],),
                      (CriterionSpec("identity","bad",self.checks["identity"]),self.specs[1]),
                      (CriterionSpec("identity",digest(b"x"),True),self.specs[1])):
            with self.assertRaises(ValueError):
                build_review_plan(self.h,specs)

    def test_halt_before_checks_and_after_callback(self):
        for state in (None,True,0):
            with self.assertRaises(PermissionError):
                self.review(halted=state)
        self.checks["identity"].assert_not_called()
        flag=[False]
        def stop(_raw):
            flag[0]=True
            return True
        self.checks["identity"].side_effect=stop
        with self.assertRaises(PermissionError):
            self.review(halt_check=lambda:flag[0])
        self.checks["source"].assert_not_called()

    def test_mutated_plan_and_forged_handoff_rejected(self):
        plan=build_review_plan(self.h,self.specs)
        with self.assertRaises(ValueError):
            self.review(plan=replace(plan,specs=plan.specs[:1]))
        with self.assertRaises(ValueError):
            self.review(h=replace(self.h,attempt=4))
        for check in self.checks.values():
            check.assert_not_called()
