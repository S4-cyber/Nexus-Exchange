import json
import unittest
from datetime import date, datetime, timezone, timedelta
from nexus_exchange.sam_discovery import Search, parse_pages, MAX_BYTES

NOW = datetime(2026, 11, 24, 18, tzinfo=timezone.utc)
RETRIEVED = NOW.isoformat()
SEARCH = Search(date(2026,11,1),date(2026,11,24),"digital services",2,3)

def row(i=1, **overrides):
    return dict(noticeId=f"{i:032x}", title="Digital services", type="Solicitation",
        active="Yes", responseDeadLine="2026-12-01T15:00:00-05:00",
        fullParentPathName="Synthetic agency", solicitationNumber="TEST-1",
        naicsCode="541511", typeOfSetAside="SBA", **{}) | overrides

def page(rows, total=None, offset=0, limit=2):
    return json.dumps(dict(totalRecords=len(rows) if total is None else total,
        limit=limit, offset=offset, opportunitiesData=rows)).encode()

def parse(*pages, **kwargs):
    return parse_pages(SEARCH, pages, retrieved_at=RETRIEVED,
                       now=NOW, halted=False, **kwargs)

class SamTests(unittest.TestCase):
    def test_request_no_secret_and_page_index(self):
        p=SEARCH.params(1)
        self.assertEqual(p["offset"],1)
        self.assertEqual(p["postedFrom"],"11/01/2026")
        self.assertNotIn("api_key",p)
        for index in (-1,3,True):
            with self.assertRaises(ValueError): SEARCH.params(index)

    def test_invalid_search_limits(self):
        for search in (Search(date(2025,1,1),NOW.date(),"test"),
                       Search(NOW.date(),NOW.date(),"test",101),
                       Search(NOW.date(),NOW.date(),"test",True),
                       Search(NOW.date(),NOW.date(),"test",1,11)):
            with self.assertRaises(ValueError): search.params(0)

    def test_provenance_and_missing_value(self):
        result=parse(page([row(award={"amount":100000},pointOfContact=[{"email":"secret@example.test"}],
                               uiLink="https://evil.example/?api_key=secret")]))
        n=result.notices[0]
        self.assertTrue(result.complete)
        self.assertEqual(len(n.page_digest),64)
        self.assertIsNone(n.opportunity.amount)
        self.assertEqual(n.opportunity.deadline.hour,20)
        self.assertFalse(n.reviewable)
        self.assertIn("SOURCE_AUTHENTICATION_REQUIRED",n.reasons)
        self.assertNotIn("secret",repr(result))
        self.assertEqual(n.opportunity.source_url,"https://sam.gov/opp/"+f"{1:032x}"+"/view")

    def test_notice_types_active_and_deadline(self):
        n=parse(page([row(type="Award Notice",active="No",responseDeadLine="2026-12-01")])).notices[0]
        self.assertIn("NOT_SOLICITATION",n.reasons)
        self.assertIn("NOT_EXPLICITLY_ACTIVE",n.reasons)
        self.assertIn("MISSING_DEADLINE",n.reasons)

    def test_complete_and_partial_pagination(self):
        first=page([row(1),row(2)],3)
        second=page([row(3)],3,1)
        self.assertFalse(parse(first).complete)
        self.assertTrue(parse(first,second).complete)
        self.assertTrue(parse(page([])).complete)

    def test_invalid_pagination(self):
        first=page([row(1),row(2)],3)
        for invalid in (page([row(1)],3,1),page([row(3)],4,1),
                        page([row(3)],3,0),page([],3,1)):
            with self.assertRaises(ValueError): parse(first,invalid)
        with self.assertRaises(ValueError): parse(page([row(1)],3))
        with self.assertRaises(ValueError): parse(page([row(1),row(1)]))

    def test_untrusted_json(self):
        for invalid in (b'{"offset":0,"offset":1}',b'{"x":NaN}',b'\xff',
                        b' '* (MAX_BYTES+1),b'['*2000+b']'*2000,
                        page([row(noticeId="../evil")]),page([row(naicsCode="abc")])):
            with self.assertRaises(ValueError): parse(invalid)

    def test_halt_future_and_stale(self):
        for halted in (True,None,0):
            with self.assertRaises(PermissionError):
                parse_pages(SEARCH,[page([])],retrieved_at=RETRIEVED,now=NOW,halted=halted)
        with self.assertRaises(ValueError):
            parse_pages(SEARCH,[page([])],retrieved_at=(NOW+timedelta(seconds=1)).isoformat(),now=NOW,halted=False)
        result=parse_pages(SEARCH,[page([row()])],retrieved_at=(NOW-timedelta(days=2)).isoformat(),now=NOW,halted=False)
        self.assertIn("STALE_OBSERVATION",result.notices[0].reasons)
