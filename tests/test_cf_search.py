import json
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch,Mock

from nexus_exchange.cf_search import CfQuery,search,notice_url,PAGE_SIZE,MAX_BYTES
from nexus_exchange.governor import Action,decide,decide_cf_read
from nexus_exchange.lead_store import LeadStore
from nexus_exchange.owner_profile import normalize_profile
from nexus_exchange.sam_search import SearchError
from nexus_exchange.trade_registry import readiness,get_source

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
QUERY=CfQuery(NOW-timedelta(hours=12),NOW,"72")
GUID="e3367511-68b1-44c1-944f-fdcf11c4ca52"
OCID="ocds-b5fd17-b681717c-f085-4a3b-9ef1-aae547fb1728"
OPTS=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW)


def release(version=1,*,hours=2,tag="tender",status="active",code="72200000"):
    return dict(id=GUID+"-"+str(version),ocid=OCID,
        date=(NOW-timedelta(hours=hours)).isoformat(),tag=[tag],initiationType="tender",
        tender=dict(title="Synthetic software services",status=status,
                    classification=dict(scheme="CPV",id=code),
                    tenderPeriod=dict(endDate=(NOW+timedelta(days=7)).isoformat()),
                    documents=[dict(url="https://evil.example/")]),
        parties=[dict(contactPoint=dict(email="private@example.test"))])


def page(rows,links=None):
    return json.dumps(dict(version="1.1",releases=rows,links=links or {})).encode()


class CfTests(unittest.TestCase):
    def run_page(self,rows,links=None,query=QUERY):
        return search(query,transport=Mock(return_value=(200,page(rows,links))),**OPTS)

    def test_exact_scope_and_research_only(self):
        report=self.run_page([release()])
        row=report["leads"][0]
        self.assertTrue(row["research_candidate"])
        self.assertFalse(row["execution_eligible"])
        self.assertFalse(row["external_authority"])
        self.assertIsNone(row["cash_exposure"])
        self.assertEqual(row["notice_id"],GUID+"-1")
        self.assertEqual(row["source_url"],"https://www.contractsfinder.service.gov.uk/Notice/"+GUID)
        self.assertEqual(row["reported_codes"],[dict(scheme="CPV",code="72200000")])
        self.assertNotIn("private@example.test",repr(report))
        self.assertNotIn("evil.example",repr(report))
        self.assertNotIn("stages",report["query"])
        self.assertNotIn("cpv",report["query"])

    def test_later_award_blocks_earlier_tender(self):
        report=self.run_page([release(hours=5),release(2,hours=1,tag="award",status="complete")])
        rows={row["notice_id"]:row for row in report["leads"]}
        self.assertIn("SUPERSEDED_WITHIN_COLLECTED_WINDOW",rows[GUID+"-1"]["blockers"])
        self.assertFalse(any(row["research_candidate"] for row in rows.values()))

    def test_ambiguous_and_incomplete_windows(self):
        self.assertFalse(any(row["research_candidate"] for row in self.run_page(
            [release(),release(2)])["leads"]))
        transport=Mock(return_value=(200,page([release()],dict(next="https://evil.example/"))))
        report=search(QUERY,transport=transport,**OPTS)
        self.assertTrue(report["truncated"])
        self.assertFalse(report["leads"][0]["research_candidate"])
        self.assertIn("COLLECTION_WINDOW_INCOMPLETE",report["leads"][0]["blockers"])
        transport.assert_called_once_with(QUERY.parameters(NOW))
        full=self.run_page([release(i+1) for i in range(PAGE_SIZE)])
        self.assertTrue(full["truncated"])

    def test_missing_cpv_mismatch_deadline_and_outside_window(self):
        missing=release()
        del missing["tender"]["classification"]
        expired=release()
        expired["tender"]["tenderPeriod"]["endDate"]=NOW.isoformat()
        no_deadline=release()
        del no_deadline["tender"]["tenderPeriod"]
        for row,reason in ((missing,"CPV_CLASSIFICATION_UNVERIFIED"),
                           (release(code="45000000"),"REQUESTED_CPV_PREFIX_NOT_REPORTED"),
                           (expired,"REPORTED_DEADLINE_PASSED"),
                           (no_deadline,"REPORTED_DEADLINE_UNVERIFIED"),
                           (release(hours=13),"PUBLICATION_OUTSIDE_WINDOW")):
            with self.subTest(reason=reason):
                lead=self.run_page([row])["leads"][0]
                self.assertFalse(lead["research_candidate"])
                self.assertIn(reason,lead["blockers"])

    def test_conflicting_duplicate_and_invalid_identifiers(self):
        first=release()
        changed=release(status="complete")
        with self.assertRaises(SearchError):
            self.run_page([first,changed])
        self.assertEqual(self.run_page([first,first])["returned"],1)
        for bad in (GUID,GUID+"-0",GUID+"-1/../","https://evil.example/"):
            with self.assertRaises(ValueError):
                notice_url(bad)
            with self.assertRaises(SearchError):
                self.run_page([dict(first,id=bad)])

    def test_halt_and_consent_before_request(self):
        transport=Mock()
        for approved,state in ((None,False),(1,False),(True,None),(True,True),(True,0)):
            with self.assertRaises(PermissionError):
                search(QUERY,transport=transport,approved=approved,halt_check=lambda:state)
        transport.assert_not_called()
        self.assertFalse(decide_cf_read(approved=True,halted=False).external_authority)
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)

    def test_bounded_query_and_no_retry(self):
        for query in (CfQuery(NOW-timedelta(days=2),NOW,"72"),CfQuery(NOW,NOW,"72"),
                      CfQuery(NOW-timedelta(hours=1),NOW,"72*")):
            with self.assertRaises(ValueError):
                search(query,transport=Mock(),**OPTS)
        for status in (301,403,429,503,500,True):
            transport=Mock(return_value=(status,b""))
            with self.assertRaises(SearchError):
                search(QUERY,transport=transport,**OPTS)
            transport.assert_called_once()

    def test_halt_during_response_suppresses_report(self):
        halted=False
        def transport(params):
            nonlocal halted
            halted=True
            return 200,page([release()])
        with self.assertRaises(PermissionError):
            search(QUERY,transport=transport,**(OPTS|dict(halt_check=lambda:halted)))

    def test_invalid_package_and_byte_bounds(self):
        for raw in (b'{"version":"1.1","version":"1.0","releases":[]}',
                    b'{"version":"1.0","releases":[]}',b'{}',b"x"*(MAX_BYTES+1)):
            with self.assertRaises(SearchError):
                search(QUERY,transport=Mock(return_value=(200,raw)),**OPTS)

    def test_fixed_get_and_cooldown(self):
        with patch("nexus_exchange.cf_search._NEXT_REQUEST_NS",0), \
             patch("nexus_exchange.cf_search.monotonic_ns",side_effect=[1,2,3]), \
             patch("nexus_exchange.cf_search.http.client.HTTPSConnection") as factory:
            conn=factory.return_value
            response=conn.getresponse.return_value
            response.status=429
            with self.assertRaises(SearchError):
                search(QUERY,**OPTS)
            with self.assertRaisesRegex(SearchError,"CF_LOCAL_COOLDOWN"):
                search(QUERY,**OPTS)
            factory.assert_called_once_with("www.contractsfinder.service.gov.uk",443,timeout=10)
            args=conn.request.call_args.args
            self.assertEqual(args[0],"GET")
            self.assertTrue(args[1].startswith("/Published/Notices/OCDS/Search?"))
            self.assertNotIn("stages=",args[1])
            response.read.assert_not_called()
            conn.close.assert_called_once()

    def test_archive_and_profile_real_integration(self):
        profile=normalize_profile(dict(mode="genesis",budget="0",hours_per_week=20,
            sources=["uk_contracts"],naics=[],cpv=["72"],keywords=[]))
        with LeadStore(":memory:") as store:
            report=self.run_page([release(hours=5)])
            self.assertEqual(store.record(report,now=NOW,halted=False),1)
            rows=store.browse(now=NOW,profile=profile,source="uk_contracts",halted=False)["leads"]
            self.assertEqual(rows[0]["profile_fit"]["reason"],"DECLARED_CLASSIFICATION_MATCH")
            self.assertFalse(rows[0]["execution_eligible"])
            self.assertEqual(rows[0]["ocid"],OCID)
            self.assertEqual(store.record(self.run_page([release(2,hours=1,tag="award",status="complete")]),
                                          now=NOW,halted=False),1)
            rows=store.browse(now=NOW,profile=profile,source="uk_contracts",halted=False)["leads"]
            old=next(row for row in rows if row["notice_id"]==GUID+"-1")
            self.assertIn("LATER_UK_EVENT_IN_ARCHIVE",old["blockers"])
            self.assertEqual(old["profile_fit"]["reason"],"REFRESH_OR_BLOCKED")

    def test_catalog_keeps_freelancer_permission_gate(self):
        self.assertIn("Contracts Finder one-page",readiness("uk_contracts",halted=False)["adapter_status"])
        self.assertIn("express written permission",get_source("freelancer").scope)
        self.assertFalse(readiness("freelancer",halted=False)["external_authority"])

if __name__=="__main__":
    unittest.main()
