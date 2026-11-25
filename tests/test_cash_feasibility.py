import unittest
from decimal import Decimal, localcontext
from nexus_exchange.lead_store import LeadStore
from nexus_exchange.cash_feasibility import assess, COSTS
from test_lead_store import NOW, reports
from test_owner_profile import profile

def scenario(**kw):
    raw=dict(currency="USD",compensation="200.00",probability_delivery_bps=8000,
        probability_payment_given_delivery_bps=7500,delivery_days=7,payment_days_after_delivery=30,
        labor_hours=10,costs=dict.fromkeys(COSTS,"0.00"))
    raw.update(kw)
    return raw

class CashFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.store=LeadStore(":memory:")
        self.addCleanup(self.store.__exit__,None,None,None)
        self.store.record(reports()[0],now=NOW,halted=False)
        self.profile=profile(mode="genesis",budget="0",hours_per_week=20)
        self.lead=self.store.browse(now=NOW,source="sam",profile=self.profile,halted=False)["leads"][0]

    def run_model(self,raw=None,**kw):
        args=dict(lead=self.lead,profile=self.profile,scenario=scenario() if raw is None else raw,halted=False)
        args.update(kw)
        return assess(**args)

    def test_zero_cost_model_is_not_verified(self):
        r=self.run_model()
        self.assertEqual(r["modeled_cash_exposure"],Decimal("0"))
        self.assertEqual(r["modeled_expected_net"],Decimal("120"))
        self.assertTrue(r["modeled_budget_fit"])
        self.assertTrue(r["modeled_hours_fit"])
        self.assertEqual(r["modeled_days_to_payment"],37)
        for k in ("independently_verified","execution_eligible","external_authority","genesis_verified"):
            self.assertIs(r[k],False)

    def test_unknown_cost_never_zero(self):
        costs=dict.fromkeys(COSTS,"0")
        costs["platform_fees"]=None
        r=self.run_model(scenario(costs=costs))
        self.assertIsNone(r["modeled_cash_exposure"])
        self.assertIsNone(r["modeled_expected_net"])
        self.assertIsNone(r["modeled_budget_fit"])
        self.assertIn("COST_UNKNOWN:platform_fees",r["reasons"])

    def test_all_costs_reserved_even_when_payment_fails(self):
        costs=dict.fromkeys(COSTS,"1.25")
        r=self.run_model(scenario(costs=costs,probability_payment_given_delivery_bps=0))
        self.assertEqual(r["modeled_cash_exposure"],Decimal("1.25")*len(COSTS))
        self.assertEqual(r["modeled_expected_net"],-r["modeled_cash_exposure"])
        self.assertFalse(r["modeled_budget_fit"])

    def test_unknown_terms_and_time(self):
        r=self.run_model(scenario(compensation=None,payment_days_after_delivery=None,labor_hours=None))
        self.assertIsNone(r["modeled_expected_net"])
        self.assertIsNone(r["modeled_days_to_payment"])
        self.assertIsNone(r["modeled_hours_fit"])

    def test_low_precision(self):
        with localcontext() as ctx:
            ctx.prec=2
            r=self.run_model(scenario(compensation="123456.78",probability_delivery_bps=1234,
                probability_payment_given_delivery_bps=5678))
        self.assertEqual(r["modeled_expected_net"],Decimal("8650.1869450056"))

    def test_funded_profile_and_mismatch(self):
        p=profile(mode="catalyst",budget="25",hours_per_week=20)
        with self.assertRaises(ValueError):
            self.run_model(profile=p)
        lead=self.store.browse(now=NOW,source="sam",profile=p,halted=False)["leads"][0]
        costs=dict.fromkeys(COSTS,"0")
        costs["software"]="25.01"
        r=self.run_model(scenario(costs=costs),lead=lead,profile=p)
        self.assertFalse(r["modeled_budget_fit"])
        costs["software"]="25"
        self.assertTrue(self.run_model(scenario(costs=costs),lead=lead,profile=p)["modeled_budget_fit"])

    def test_hours_and_zero_days(self):
        self.assertFalse(self.run_model(scenario(labor_hours=21))["modeled_hours_fit"])
        self.assertFalse(self.run_model(scenario(delivery_days=0,labor_hours=1))["modeled_hours_fit"])

    def test_malformed_and_halt(self):
        for raw in (scenario(compensation=True),scenario(compensation="1e3"),scenario(currency="EUR"),
            scenario(costs={}),scenario(labor_hours=True),scenario(delivery_days=-1),
            scenario(probability_delivery_bps=10001)):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                self.run_model(raw)
        for halted in (True,None,0):
            with self.assertRaises(PermissionError):
                self.run_model(halted=halted)

    def test_context_and_digest(self):
        a=self.run_model()
        b=self.run_model(scenario(compensation="201"))
        self.assertNotEqual(a["scenario_sha256"],b["scenario_sha256"])
        self.assertEqual(a["context"],b["context"])
        self.assertEqual(a["scenario_sha256"],self.run_model(scenario(compensation="200"))["scenario_sha256"])
        forged=dict(self.lead,external_authority=True)
        with self.assertRaises(ValueError):
            self.run_model(lead=forged)
