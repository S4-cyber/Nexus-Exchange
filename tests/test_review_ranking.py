import copy
import unittest
from datetime import timedelta
from decimal import localcontext
from unittest.mock import Mock
from nexus_exchange.checklist_store import context_for
from nexus_exchange.review_ranking import RankingStore
from nexus_exchange import sam_search, usaspending_search
import test_sam_search as sam
import test_usaspending_search as spending
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW, reports
from test_owner_profile import profile


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.store=RankingStore(":memory:")
        self.addCleanup(self.store.__exit__,None,None,None)
        self.profile=profile()
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(i) for i in range(1,4)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        self.store.record(self.report,now=NOW,halted=False)

    def rows(self,now=NOW):
        return self.store.browse(now=now,profile=self.profile,source="sam",halted=False)["leads"]

    def save(self,index,raw=None,timing=None,now=NOW):
        row=self.rows(now)[index]
        return self.store.save(context_for(row),scenario() if raw is None else raw,
            plan() if timing is None else timing,profile=self.profile,now=now,halted=False)

    def rank(self,**kw):
        args=dict(profile=self.profile,now=NOW,halted=False)
        args.update(kw)
        return self.store.rank_review(**args)

    def test_missing_plan_is_not_zero_or_ready(self):
        result=self.rank()
        self.assertEqual(result["returned"],3)
        for row in result["rows"]:
            self.assertEqual(row["review_tier"],"MODEL_UNRESOLVED")
            self.assertIsNone(row["modeled_cash_exposure"])
            self.assertIsNone(row["plan_id"])
            self.assertIn("NO_CURRENT_SCENARIO",row["reasons"])
            self.assertFalse(row["execution_eligible"])
            self.assertFalse(row["independently_verified"])

    def test_positive_model_precedes_unknown_and_negative(self):
        good=self.save(1)
        bad=self.save(0,scenario(compensation="0"))
        rows=self.rank()["rows"]
        self.assertEqual([r["review_tier"] for r in rows],
            ["MODEL_FITS_UNVERIFIED","MODEL_UNRESOLVED","MODEL_DOES_NOT_FIT"])
        self.assertEqual(rows[0]["plan_id"],good)
        self.assertEqual(rows[-1]["plan_id"],bad)
        self.assertTrue(all(not r["external_authority"] for r in rows))

    def test_incomplete_costs_and_payment_never_fit(self):
        costs=scenario()["costs"]
        costs["software"]=None
        key=self.save(0,scenario(costs=costs))
        self.save(1,scenario(payment_days_after_delivery=None))
        rows=self.rank()["rows"]
        self.assertTrue(all(r["review_tier"]=="MODEL_UNRESOLVED" for r in rows))
        target=next(r for r in rows if r["plan_id"]==key)
        self.assertIsNone(target["modeled_cash_exposure"])

    def test_source_refresh_overrides_financial_fit(self):
        key=self.save(0)
        row=next(r for r in self.rank(now=NOW+timedelta(days=2))["rows"] if r["plan_id"]==key)
        self.assertEqual(row["review_tier"],"SOURCE_REVIEW_REQUIRED")
        self.assertIn("OBSERVATION_STALE",row["reasons"])

    def test_new_observation_does_not_inherit_plan(self):
        key=self.save(0)
        later=NOW+timedelta(minutes=1)
        report=copy.deepcopy(self.report)
        for row in report["leads"]:
            row["retrieved_at"]=later.isoformat()
        self.store.record(report,now=later,halted=False)
        result=self.rank(now=later)
        self.assertNotIn(key,[r["plan_id"] for r in result["rows"]])
        self.assertTrue(all(r["plan_id"] is None for r in result["rows"]))

    def test_no_optimistic_plan_selection(self):
        old=self.save(0,scenario(compensation="1000"))
        new=self.save(0,scenario(compensation="0"),now=NOW+timedelta(minutes=1))
        row=next(r for r in self.rank(now=NOW+timedelta(minutes=1))["rows"] if r["plan_id"]==new)
        self.assertEqual(row["review_tier"],"MODEL_DOES_NOT_FIT")
        self.assertNotEqual(row["plan_id"],old)

    def test_equal_time_distinct_plans_are_ambiguous(self):
        self.save(0,scenario(compensation="1000"))
        self.save(0,scenario(compensation="0"))
        row=next(r for r in self.rank()["rows"] if "LATEST_SCENARIO_AMBIGUOUS" in r["reasons"])
        self.assertIsNone(row["plan_id"])
        self.assertEqual(row["review_tier"],"MODEL_UNRESOLVED")

    def test_future_saved_plan_cannot_rank(self):
        self.save(0,now=NOW+timedelta(minutes=1))
        row=next(r for r in self.rank()["rows"] if "SCENARIO_IN_FUTURE" in r["reasons"])
        self.assertEqual(row["review_tier"],"MODEL_UNRESOLVED")

    def test_smaller_exposure_then_payment_then_net(self):
        self.profile=profile(mode="catalyst",budget="50")
        costs=scenario()["costs"]
        costs["software"]="1"
        expensive=self.save(0,scenario(compensation="5000",costs=costs))
        slow=self.save(1,scenario(compensation="500",payment_days_after_delivery=60))
        fast=self.save(2,scenario(compensation="200",payment_days_after_delivery=5))
        rows=self.rank()["rows"]
        self.assertEqual([r["plan_id"] for r in rows],[fast,slow,expensive])
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual([r["plan_id"] for r in self.rank()["rows"]],[fast,slow,expensive])

    def test_awards_and_unselected_source_remain_separate(self):
        report=usaspending_search.search(spending.QUERY,approved=True,halt_check=lambda:False,
            clock=lambda:NOW,transport=Mock(return_value=(200,spending.page([spending.award()]))))
        self.store.record(report,now=NOW,halted=False)
        result=self.rank()
        award=next(r for r in result["rows"] if r["source"]=="usaspending")
        self.assertEqual(award["review_tier"],"CONTRACTOR_INTELLIGENCE_ONLY")
        self.assertEqual(self.rank(profile=profile(sources=[]))["rows"][0]["review_tier"],"SOURCE_NOT_SELECTED")

    def test_bounded_scan_reports_truncation(self):
        result=self.rank(limit=1,scan_limit=2)
        self.assertEqual(result["matched"],3)
        self.assertEqual(result["evaluated"],2)
        self.assertEqual(result["returned"],1)
        self.assertTrue(result["scan_truncated"])
        self.assertTrue(result["output_truncated"])
        self.assertFalse(result["global_ranking"])

    def test_halt_and_bad_limits(self):
        for halted in (True,None,0):
            with self.assertRaises(PermissionError):
                self.rank(halted=halted)
        for kw in (dict(limit=True),dict(scan_limit=101),dict(limit=3,scan_limit=2),dict(profile=None)):
            with self.assertRaises(ValueError):
                self.rank(**kw)
        self.assertFalse(self.store.db.in_transaction)

    def test_genesis_rejects_positive_cash_exposure(self):
        costs=scenario()["costs"]
        costs["platform_fees"]="0.01"
        key=self.save(0,scenario(compensation="999999",costs=costs))
        row=next(r for r in self.rank()["rows"] if r["plan_id"]==key)
        self.assertEqual(row["review_tier"],"MODEL_DOES_NOT_FIT")
        self.assertFalse(row["modeled_budget_fit"])
        self.assertFalse(row["genesis_verified"])

    def test_payment_wait_includes_delayed_start(self):
        first=self.save(0,scenario(payment_days_after_delivery=10))
        second=self.save(1,scenario(payment_days_after_delivery=1),
            plan(delivery_start="2026-12-20T12:00:00Z",delivery_deadline="2026-12-28T12:00:00Z"))
        rows=self.rank()["rows"]
        self.assertEqual([r["plan_id"] for r in rows[:2]],[first,second])
        self.assertLess(rows[0]["modeled_collection_wait_us"],rows[1]["modeled_collection_wait_us"])

    def test_corrupt_plan_fails_closed_and_read_transaction_rolls_back(self):
        key=self.save(0)
        self.store.db.execute("UPDATE scout_scenarios_v1 SET payload='{}' WHERE plan_id=?",(key,))
        with self.assertRaises(ValueError):
            self.rank()
        self.assertFalse(self.store.db.in_transaction)
