import unittest
from decimal import Decimal
from nexus_exchange.revenue_pathways import Mode, plan_lead, source_url, CHECKS

ALL = tuple(key for key,_ in CHECKS)

class PathwayTests(unittest.TestCase):
    def test_zero_capital_default_blocks_unknown_cost(self):
        result = plan_lead(Mode.GENESIS,"sam",halted=False)
        self.assertEqual(result.budget,Decimal(0))
        self.assertIn("CASH_EXPOSURE_UNKNOWN",result.reasons)
        self.assertIn("CHECKLIST_INCOMPLETE",result.reasons)
        self.assertFalse(result.ready_for_review)

    def test_zero_cost_and_checklist_allow_review_only(self):
        result=plan_lead(Mode.GENESIS,"subnet",exposure="0",confirmed=ALL,halted=False)
        self.assertTrue(result.ready_for_review)
        self.assertFalse(result.external_authority)
        self.assertTrue(all(task.status=="asserted; verification required" for task in result.tasks))

    def test_zero_capital_rejects_positive_cost(self):
        result=plan_lead(Mode.GENESIS,"sam",exposure="0.01",confirmed=ALL,halted=False)
        self.assertIn("EXPOSURE_EXCEEDS_BUDGET",result.reasons)
        self.assertFalse(result.ready_for_review)
        with self.assertRaises(ValueError):
            plan_lead(Mode.GENESIS,"sam",budget="1",halted=False)

    def test_funded_planning_is_not_bank_authority(self):
        result=plan_lead(Mode.CATALYST,"sam",budget="100",exposure="50",confirmed=ALL,halted=False)
        self.assertTrue(result.ready_for_review)
        self.assertFalse(result.external_authority)
        result=plan_lead(Mode.CATALYST,"sam",budget="100",exposure="100.01",confirmed=ALL,halted=False)
        self.assertFalse(result.ready_for_review)

    def test_grants_are_not_earned_revenue(self):
        result=plan_lead(Mode.GENESIS,"grants",exposure="0",confirmed=ALL,halted=False)
        self.assertIn("RESTRICTED_FUNDING_NOT_REVENUE",result.reasons)
        self.assertFalse(result.ready_for_review)

    def test_approved_source_urls_only(self):
        self.assertEqual(source_url("sam"),"https://sam.gov/opportunities")
        for bad in ("https://evil.example","SAM","sam/../other",None):
            with self.assertRaises(ValueError):
                source_url(bad)

    def test_invalid_inputs_fail_closed(self):
        for kwargs in (dict(budget="-1"),dict(exposure="NaN"),dict(exposure=0),
                       dict(confirmed=["unknown"]),dict(confirmed=["source","source"])):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                plan_lead(Mode.CATALYST,"sam",halted=False,**kwargs)
        for state in (None,True,0):
            with self.assertRaises(PermissionError):
                plan_lead(Mode.GENESIS,"sam",halted=state)
