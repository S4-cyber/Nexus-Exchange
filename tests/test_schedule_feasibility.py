import unittest
from datetime import datetime, timedelta, timezone
from nexus_exchange.lead_store import LeadStore
from nexus_exchange.schedule_feasibility import assess_schedule
from test_lead_store import NOW, reports
from test_owner_profile import profile
from test_cash_feasibility import scenario


def plan(**kw):
    raw=dict(preparation_days=2, preparation_hours=4,
             delivery_start="2026-12-05T12:00:00Z",
             delivery_deadline="2026-12-12T12:00:00Z")
    raw.update(kw)
    return raw


class ScheduleFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.store=LeadStore(":memory:")
        self.addCleanup(self.store.__exit__,None,None,None)
        self.store.record(reports()[0],now=NOW,halted=False)
        self.profile=profile(mode="genesis",budget="0",hours_per_week=20)
        self.lead=self.store.browse(now=NOW,source="sam",profile=self.profile,halted=False)["leads"][0]

    def run_plan(self,raw=None,**kw):
        args=dict(lead=self.lead,profile=self.profile,scenario=scenario(),
                  plan=plan() if raw is None else raw,now=NOW,halted=False)
        args.update(kw)
        return assess_schedule(**args)

    def test_submission_and_delivery_are_distinct(self):
        r=self.run_plan()
        self.assertTrue(r["modeled_submission_fit"])
        self.assertTrue(r["modeled_delivery_deadline_fit"])
        self.assertTrue(r["modeled_schedule_fit"])
        self.assertEqual(r["modeled_delivery_finish"],"2026-12-12T12:00:00.000000+00:00")
        for k in ("independently_verified","execution_eligible","external_authority","genesis_verified"):
            self.assertIs(r[k],False)
        self.assertIn("SCHEDULE_ASSUMPTIONS_NOT_VERIFIED",r["reasons"])

    def test_submission_strict_cutoff(self):
        r=self.run_plan(plan(preparation_days=7))
        self.assertFalse(r["modeled_submission_fit"])
        self.assertFalse(r["modeled_schedule_fit"])
        self.assertIn("MODELED_SUBMISSION_MISSES_DEADLINE",r["reasons"])

    def test_contract_deadline_not_tender_deadline(self):
        r=self.run_plan(plan(delivery_deadline=None))
        self.assertIsNone(r["modeled_delivery_deadline_fit"])
        self.assertIsNone(r["modeled_schedule_fit"])
        self.assertIn("DELIVERY_DEADLINE_UNKNOWN",r["reasons"])
        r=self.run_plan(plan(delivery_deadline="2026-12-12T11:59:59Z"))
        self.assertFalse(r["modeled_delivery_deadline_fit"])

    def test_date_only_is_not_precise_cutoff(self):
        lead=dict(self.lead,deadline=None,earliest_deadline_date="2026-12-01")
        r=self.run_plan(lead=lead)
        self.assertIsNone(r["modeled_submission_fit"])
        self.assertIsNone(r["modeled_schedule_fit"])
        self.assertIn("SUBMISSION_DEADLINE_UNRESOLVED",r["reasons"])

    def test_expired_source_deadline(self):
        r=self.run_plan(now=NOW+timedelta(days=7))
        self.assertFalse(r["modeled_submission_fit"])
        self.assertIn("REPORTED_SUBMISSION_DEADLINE_PASSED",r["reasons"])

    def test_preparation_and_delivery_capacity(self):
        r=self.run_plan(plan(preparation_hours=6))
        self.assertFalse(r["modeled_preparation_hours_fit"])
        self.assertFalse(r["modeled_schedule_fit"])
        r=self.run_plan(scenario=scenario(labor_hours=21))
        self.assertFalse(r["modeled_schedule_fit"])

    def test_order_and_unknown_inputs(self):
        r=self.run_plan(plan(delivery_start="2026-11-25T12:00:00Z"))
        self.assertFalse(r["modeled_sequence_fit"])
        r=self.run_plan(plan(preparation_days=None))
        self.assertIsNone(r["modeled_submission_fit"])
        self.assertIsNone(r["modeled_schedule_fit"])

    def test_digest_binds_plan_finance_and_clock(self):
        a=self.run_plan()
        self.assertEqual(a["schedule_sha256"],self.run_plan(
            plan(delivery_start="2026-12-05T04:00:00-08:00"))["schedule_sha256"])
        self.assertNotEqual(a["schedule_sha256"],self.run_plan(plan(preparation_hours=3))["schedule_sha256"])
        self.assertNotEqual(a["schedule_sha256"],self.run_plan(scenario=scenario(compensation="201"))["schedule_sha256"])
        self.assertNotEqual(a["schedule_sha256"],self.run_plan(now=NOW+timedelta(seconds=1))["schedule_sha256"])

    def test_bad_inputs_and_halt(self):
        for raw in (plan(preparation_days=True),plan(preparation_hours=-1),
                    plan(delivery_start="2026-12-05T12:00:00"),
                    plan(delivery_start="9999-12-31T12:00:00Z"),dict(plan(),extra=True)):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                self.run_plan(raw)
        for clock in (NOW.replace(tzinfo=None),NOW-timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                self.run_plan(now=clock)
        for halted in (True,None,0):
            with self.assertRaises(PermissionError):
                self.run_plan(halted=halted)

    def test_authority_never_inherited_and_awards_not_solicitations(self):
        lead=dict(self.lead,external_authority=True)
        with self.assertRaises(ValueError):
            self.run_plan(lead=lead)
        self.assertIn("HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED",self.run_plan()["reasons"])
