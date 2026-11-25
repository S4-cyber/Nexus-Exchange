import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nexus_exchange import sam_search, ted_search, fts_search, cf_search, canada_search
from nexus_exchange.lead_store import _digest,_json
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.operator_capabilities import CSV_ID,JSON_ID,PROFILE_ID,RECONCILE_ID
from nexus_exchange.scout_discovery import build_plan,resolve_query,execute_discovery,load_profile,READY,MAX_OPTIONS,TTL

NOW=datetime(2026,11,25,12,34,56,123456,tzinfo=timezone.utc)


def profile(**changes):
    return dict(dict(mode="genesis",budget="0",hours_per_week=20,
        sources=["sam","ted","uk_tender","uk_contracts","canada","usaspending"],
        naics=["541519"],cpv=["72","79"],keywords=["unrelated private preference"]),**changes)


class DiscoveryTests(unittest.TestCase):
    def plan(self,capability=CSV_ID,p=None):
        return build_plan(profile() if p is None else p,capability,now=NOW,halted=False)

    def test_four_service_plans_deterministic_and_bounded(self):
        for capability,phrase in ((CSV_ID,"csv sorting"),(JSON_ID,"json to csv"),
                                 (PROFILE_ID,"csv quality report"),(RECONCILE_ID,"csv reconciliation")):
            p=self.plan(capability)
            self.assertEqual(p,self.plan(capability))
            self.assertEqual(len(p["options"]),9)
            self.assertEqual({r["filter_value"] for r in p["options"] if r["source"] in ("sam","canada")},{phrase})
            self.assertEqual({r["procurement_type"] for r in p["options"] if r["source"]=="sam"},{"k","o"})
            self.assertEqual({r["filter_value"] for r in p["options"] if r["source"]=="ted"},{"72","79"})
            self.assertEqual(len({r["option_id"] for r in p["options"]}),9)
            self.assertNotIn("unrelated private preference",repr(p))
            for flag in ("external_authority","execution_eligible","automatic_search_enabled","read_consent_granted"):
                self.assertIs(p[flag],False)
                self.assertTrue(all(row[flag] is False for row in p["options"]))

    def test_profile_sources_and_prerequisites_are_not_inferred(self):
        p=profile(sources=["ted","uk_contracts","usaspending"],cpv=[])
        plan=self.plan(p=p)
        self.assertEqual({row["state"] for row in plan["options"]},
                         {"CPV_DECLARATION_REQUIRED","CONTRACTOR_INTELLIGENCE_ONLY"})
        for row in plan["options"]:
            with self.assertRaises(ValueError):
                resolve_query(plan,row["option_id"],p,now=NOW,halted=False)
        empty=self.plan(p=profile(sources=[]))
        self.assertEqual(empty["options"],[])
        held=self.plan(p=profile(sources=["sam"],hours_per_week=0))
        self.assertEqual({r["state"] for r in held["options"]},{"NO_DECLARED_AVAILABILITY"})
        max_plan=self.plan(p=profile(cpv=[str(i) for i in range(10,42)]))
        self.assertEqual(len(max_plan["options"]),MAX_OPTIONS)

    def test_exact_typed_queries_preserve_provider_constraints(self):
        p=self.plan()
        for row in p["options"]:
            if row["state"]!=READY:
                continue
            checked,q=resolve_query(p,row["option_id"],profile(),now=NOW,halted=False)
            self.assertEqual(checked,row)
            src=row["source"]
            if src=="sam":
                self.assertIs(type(q),sam_search.Query)
                self.assertEqual(q.procurement_type,row["procurement_type"])
                self.assertEqual(row["max_requests"],3)
            elif src=="ted":
                self.assertIs(type(q),ted_search.TedQuery)
                self.assertEqual(q.cpv_prefix,row["filter_value"])
            elif src=="uk_tender":
                self.assertIs(type(q),fts_search.FtsQuery)
                self.assertEqual(q.updated_to-q.updated_from,timedelta(days=1))
                self.assertIsNone(row["filter_value"])
            elif src=="uk_contracts":
                self.assertIs(type(q),cf_search.CfQuery)
                self.assertEqual(q.published_to-q.published_from,timedelta(hours=6))
                self.assertNotIn("cpv",repr(q.parameters(NOW)).lower())
            elif src=="canada":
                self.assertIs(type(q),canada_search.CanadaQuery)
                self.assertEqual(row["max_response_bytes"],32*1024*1024)

    def test_plan_expiry_and_profile_drift_deny(self):
        p=self.plan()
        key=p["options"][0]["option_id"]
        for now in (NOW-timedelta(seconds=1),NOW+TTL+timedelta(microseconds=1)):
            with self.assertRaises(ValueError):
                resolve_query(p,key,profile(),now=now,halted=False)
        for altered in (profile(hours_per_week=1),profile(cpv=["72"]),profile(sources=["sam"])):
            with self.assertRaises(ValueError):
                resolve_query(p,key,altered,now=NOW,halted=False)
        for halted in (None,True,0):
            with self.assertRaises(PermissionError):
                resolve_query(p,key,profile(),now=NOW,halted=halted)

    def test_modified_resealed_plan_cannot_select_arbitrary_query(self):
        p=self.plan()
        bad=copy.deepcopy(p)
        row=bad["options"][0]
        row["filter_value"]="arbitrary query"
        row["option_id"]=_digest(_json({k:v for k,v in row.items() if k!="option_id"}))
        bad["plan_sha256"]=_digest(_json({k:v for k,v in bad.items() if k!="plan_sha256"}))
        with self.assertRaises(ValueError):
            resolve_query(bad,row["option_id"],profile(),now=NOW,halted=False)
        with self.assertRaises(ValueError):
            resolve_query(p,"0"*64,profile(),now=NOW,halted=False)

    def test_one_exact_adapter_per_explicit_selection_preserves_report(self):
        p=self.plan()
        modules={"sam":sam_search,"ted":ted_search,"uk_tender":fts_search,
                 "uk_contracts":cf_search,"canada":canada_search}
        for source,module in modules.items():
            row=next(r for r in p["options"] if r["source"]==source)
            sentinel={"leads":[{"blockers":["CONTRARY_FIXTURE"]}],"truncated":True}
            live=lambda:False
            key="owned-test-key" if source=="sam" else None
            with self.subTest(source=source),patch.object(module,"search",return_value=sentinel) as adapter:
                result=execute_discovery(p,row["option_id"],profile(),now=NOW,
                    approved=True,halt_check=live,api_key=key)
                self.assertIs(result,sentinel)
                _,q=resolve_query(p,row["option_id"],profile(),now=NOW,halted=False)
                args=(q,key) if source=="sam" else (q,)
                adapter.assert_called_once_with(*args,approved=True,halt_check=live)

    def test_consent_halt_credentials_and_post_fetch_halt(self):
        p=self.plan(p=profile(sources=["sam","canada"]))
        declared=profile(sources=["sam","canada"])
        sam=next(r for r in p["options"] if r["source"]=="sam")["option_id"]
        canada=next(r for r in p["options"] if r["source"]=="canada")["option_id"]
        with patch.object(sam_search,"search") as a,patch.object(canada_search,"search") as b:
            for approved in (False,None,1):
                with self.assertRaises(PermissionError):
                    execute_discovery(p,sam,declared,now=NOW,approved=approved,halt_check=lambda:False,api_key="owned-test-key")
            with self.assertRaises(PermissionError):
                execute_discovery(p,sam,declared,now=NOW,approved=True,halt_check=lambda:True,api_key="owned-test-key")
            for key in (None,"short",123):
                with self.assertRaises(ValueError):
                    execute_discovery(p,sam,declared,now=NOW,approved=True,halt_check=lambda:False,api_key=key)
            with self.assertRaises(ValueError):
                execute_discovery(p,canada,declared,now=NOW,approved=True,halt_check=lambda:False,api_key="owned-test-key")
            a.assert_not_called();b.assert_not_called()
            stopped=[False]
            def fetch(*args,**kwargs):
                stopped[0]=True
                return {"leads":[]}
            b.side_effect=fetch
            with self.assertRaises(PermissionError):
                execute_discovery(p,canada,declared,now=NOW,approved=True,halt_check=lambda:stopped[0])
            b.assert_called_once()

    def test_load_missing_profile_does_not_create_database(self):
        with TemporaryDirectory() as tmp:
            directory=Path(tmp)
            with self.assertRaises(ValueError):
                load_profile(directory,halt_check=lambda:False)
            self.assertFalse((directory/"owner-profile.sqlite3").exists())
            with ProfileStore(directory/"owner-profile.sqlite3") as store:
                store.save(profile(),halted=False)
            self.assertEqual(load_profile(directory,halt_check=lambda:False)["budget"],"0.00")
            with self.assertRaises(PermissionError):
                load_profile(directory,halt_check=lambda:None)


if __name__=="__main__":
    unittest.main()
