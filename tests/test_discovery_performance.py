import copy
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from nexus_exchange import sam_search
from nexus_exchange.lead_store import LeadStore,_json,_digest
from nexus_exchange.scout_discovery import build_plan,resolve_query
from nexus_exchange.discovery_performance import analyze,empty_history,performance_text
from nexus_exchange.discovery_history import LEGACY_FORMAT
from nexus_exchange.operator_capabilities import CSV_ID,JSON_ID
from test_scout_discovery import NOW,profile
import test_sam_search as sam


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"scout-leads.sqlite3"
        self.profile=profile(sources=["sam","canada"])
        self.counter=0

    def record(self,store,*,ptype="k",records=None,at=NOW,truncated=False):
        self.counter+=1
        plan=build_plan(self.profile,CSV_ID,now=at,halted=False)
        row=next(r for r in plan["options"] if r["source"]=="sam" and r["procurement_type"]==ptype)
        _,q=resolve_query(plan,row["option_id"],self.profile,now=at,halted=False)
        report=sam_search.search(q,sam.KEY,approved=True,halt_check=lambda:False,clock=lambda:at,
            transport=Mock(return_value=(200,sam.page([sam.notice()] if records is None else records))))
        report["truncated"]=truncated
        store.record(report,now=at,halted=False,discovery=dict(plan=plan,
            option_id=row["option_id"],profile=self.profile,started_at=at,task_id=f"{self.counter:032x}"))

    def evaluate(self,store,at=None,declared=None,capability=CSV_ID):
        at=at or NOW+timedelta(minutes=20)
        declared=declared or self.profile
        plan=build_plan(declared,capability,now=at,halted=False)
        history=store.search_history(now=at,halted=False)
        return analyze(declared,plan,history,now=at,halted=False)

    def by_type(self,result,ptype):
        return next(r for r in result["ranked_options"] if r["source"]=="sam" and r["procurement_type"]==ptype)

    def test_measured_distinct_notice_yield_not_repeat_observations(self):
        with LeadStore(self.path) as store:
            for _ in range(3):
                self.record(store)
                self.record(store,ptype="o",records=[])
            result=self.evaluate(store)
        productive=self.by_type(result,"k")
        empty=self.by_type(result,"o")
        self.assertEqual(productive["reason"],"MEASURED_REVIEW")
        self.assertEqual(productive["metrics"]["complete_requests"],3)
        self.assertEqual(productive["metrics"]["total_returned"],3)
        self.assertEqual(productive["metrics"]["distinct_notice_identities"],1)
        self.assertEqual(empty["metrics"]["distinct_notice_identities"],0)
        self.assertEqual(result["suggested_option_id"],productive["option_id"])
        self.assertEqual(result["ranked_options"][0],productive)
        self.assertFalse(result["commercial_value_verified"])
        self.assertFalse(result["automatic_search_enabled"])

    def test_recent_repeat_and_incomplete_collection_remain_advisory(self):
        with LeadStore(self.path) as store:
            self.record(store,truncated=True)
            recent=self.evaluate(store,at=NOW)
            item=self.by_type(recent,"k")
            self.assertEqual(item["reason"],"RECENT_REPEAT_REVIEW")
            self.assertTrue(item["recent_hint"]["truncated"])
            self.assertFalse(item["recent_hint"]["automatic_skip"])
            later=self.evaluate(store)
            item=self.by_type(later,"k")
            self.assertEqual(item["reason"],"INCOMPLETE_COLLECTION_REVIEW")
            self.assertEqual(item["metrics"]["complete_requests"],0)
            self.assertEqual(item["metrics"]["distinct_notice_identities"],0)
            self.assertNotEqual(later["suggested_option_id"],item["option_id"])

    def test_small_sample_not_measured_and_service_phrase_not_inferred(self):
        with LeadStore(self.path) as store:
            self.record(store)
            result=self.evaluate(store)
            self.assertEqual(self.by_type(result,"k")["reason"],"SMALL_SAMPLE_REVIEW")
            other=self.evaluate(store,capability=JSON_ID)
            self.assertEqual(self.by_type(other,"k")["reason"],"EXPLORE_UNMEASURED")

    def test_legacy_future_old_and_profile_drift_excluded(self):
        with LeadStore(self.path) as store:
            self.record(store)
            raw,=store.db.execute("SELECT payload FROM scout_search_receipts_v1").fetchone()
            import json
            legacy=json.loads(raw)
            legacy.pop("observation_refs")
            legacy["format"]=LEGACY_FORMAT
            encoded=_json(legacy)
            store.db.execute("UPDATE scout_search_receipts_v1 SET payload=?,payload_sha256=?",
                (encoded,_digest(encoded)))
            self.record(store,at=NOW+timedelta(seconds=1))
            result=self.evaluate(store,at=NOW)
            self.assertEqual(result["excluded"]["unverified"],1)
            self.assertEqual(result["excluded"]["future"],1)
            drift=self.evaluate(store,declared=dict(self.profile,hours_per_week=21))
            self.assertEqual(drift["excluded"]["different_profile_or_catalogue"],1)
            old=self.evaluate(store,at=NOW+timedelta(days=8))
            self.assertEqual(old["excluded"]["outside_lookback"],1)

    def test_held_options_and_expired_plan_have_no_suggestion(self):
        declared=profile(sources=["sam","ted"],hours_per_week=0,cpv=[])
        plan=build_plan(declared,CSV_ID,now=NOW,halted=False)
        report=analyze(declared,plan,empty_history(NOW),now=NOW,halted=False)
        self.assertIsNone(report["suggested_option_id"])
        self.assertTrue(all(r["reason"]=="HELD" for r in report["ranked_options"]))
        active=build_plan(self.profile,CSV_ID,now=NOW,halted=False)
        later=NOW+timedelta(minutes=6)
        report=analyze(self.profile,active,empty_history(later),now=later,halted=False)
        self.assertTrue(report["plan_expired"])
        self.assertIsNone(report["suggested_option_id"])

    def test_projection_rejects_changed_receipt_and_plan_and_halt(self):
        with LeadStore(self.path) as store:
            self.record(store)
            history=store.search_history(now=NOW,halted=False)
        plan=build_plan(self.profile,CSV_ID,now=NOW,halted=False)
        changed=copy.deepcopy(history)
        changed["rows"][0]["inserted"]=0
        with self.assertRaises(ValueError):
            analyze(self.profile,plan,changed,now=NOW,halted=False)
        altered=copy.deepcopy(plan)
        altered["options"][0]["filter_value"]="unreviewed"
        with self.assertRaises(ValueError):
            analyze(self.profile,altered,history,now=NOW,halted=False)
        for halted in (True,None,0):
            with self.assertRaises(PermissionError):
                analyze(self.profile,plan,history,now=NOW,halted=halted)

    def test_empty_snapshot_deterministic_and_exploration_only(self):
        plan=build_plan(self.profile,CSV_ID,now=NOW,halted=False)
        report=analyze(self.profile,plan,empty_history(NOW),now=NOW,halted=False)
        self.assertEqual(report,analyze(self.profile,plan,empty_history(NOW),now=NOW,halted=False))
        self.assertTrue(all(r["reason"]=="EXPLORE_UNMEASURED" for r in report["ranked_options"]))
        self.assertIn("not a success-rate or income model",performance_text(report))
        self.assertEqual(report["performance_sha256"],_digest(_json({
            k:v for k,v in report.items() if k!="performance_sha256"})))


if __name__=="__main__":
    unittest.main()
