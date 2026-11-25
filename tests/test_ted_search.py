import json
import unittest
from datetime import date,datetime,timezone
from unittest.mock import Mock,patch
from nexus_exchange.governor import Action,decide,decide_ted_read
from nexus_exchange.ted_search import (TedQuery,search,notice_url,_request,
    HOST,PATH,PAGE_SIZE,MAX_BYTES,SearchError)

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
QUERY=TedQuery("72",date(2026,11,10),NOW.date())

def notice(i=1,**changes):
    row={"publication-number":f"{i}-2026","publication-date":"2026-11-20+01:00",
         "notice-title":{"eng":["Synthetic IT service"]},"form-type":"competition",
         "notice-type":"cn-standard","classification-cpv":["72000000"],
         "deadline-receipt-tender-date-lot":["2026-12-03+01:00"]}
    row.update(changes)
    return row

def page(rows,total=None,**changes):
    data=dict(notices=rows,totalNoticeCount=len(rows) if total is None else total,timedOut=False)
    data.update(changes)
    return json.dumps(data).encode()

class TedTests(unittest.TestCase):
    def setUp(self):
        pacing=patch("nexus_exchange.ted_search.sleep")
        pacing.start()
        self.addCleanup(pacing.stop)

    def evaluate(self,transport,**changes):
        args=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW,transport=transport)
        args.update(changes)
        return search(QUERY,**args)

    def test_scope_and_consent(self):
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)
        self.assertFalse(decide(Action.BID,halted=False).allowed)
        self.assertFalse(decide_ted_read(approved=True,halted=False).external_authority)
        for changes in (dict(approved=None),dict(approved=1),dict(halt_check=lambda:True),
                        dict(halt_check=lambda:None)):
            transport=Mock()
            with self.assertRaises(PermissionError):
                self.evaluate(transport,**changes)
            transport.assert_not_called()

    def test_constrained_query(self):
        request=QUERY.parameters(NOW)
        self.assertEqual(request["scope"],"ACTIVE")
        self.assertIn("classification-cpv=72*",request["query"])
        self.assertEqual(request["page"],1)
        self.assertTrue(request["onlyLatestVersions"])
        for prefix in ("72* OR true","7","٧٢","72 00","123456789"):
            with self.assertRaises(ValueError):
                TedQuery(prefix,QUERY.published_from,QUERY.published_to).parameters(NOW)

    def test_date_window(self):
        for start,end in ((date(2026,1,1),NOW.date()),(NOW.date(),date(2026,11,25)),
                          (NOW.date(),date(2026,11,23))):
            with self.assertRaises(ValueError):
                TedQuery("72",start,end).parameters(NOW)

    def test_candidate_and_minimization(self):
        raw=notice(**{"links":{"html":"https://evil.example"},"buyer-email":"private@example.org",
                      "estimated-value-proc":1000000})
        report=self.evaluate(Mock(return_value=(200,page([raw]))))
        lead=report["leads"][0]
        self.assertTrue(lead["research_candidate"])
        self.assertIsNone(lead["deadline"])
        self.assertEqual(lead["earliest_deadline_date"],"2026-12-03")
        self.assertFalse(lead["execution_eligible"])
        self.assertFalse(lead["external_authority"])
        self.assertIsNone(lead["cash_exposure"])
        self.assertIn("EXACT_LOT_DEADLINE_UNVERIFIED",lead["blockers"])
        self.assertEqual(len(lead["todo"]),7)
        self.assertEqual(lead["source_url"],"https://ted.europa.eu/en/notice/-/detail/1-2026")
        for value in ("evil.example","private@example.org","1000000"):
            self.assertNotIn(value,json.dumps(report))

    def test_ambiguous_dates_and_wrong_types(self):
        cases=[
            ({"notice-type":"can-standard"},"NOT_SUPPORTED_COMPETITION"),
            ({"form-type":"result"},"NOT_SUPPORTED_COMPETITION"),
            ({"deadline-receipt-tender-date-lot":["2026-11-24+01:00","2026-12-03"]},"DEADLINE_DATE_PASSED_OR_TODAY"),
            ({"deadline-receipt-tender-date-lot":[]},"DEADLINE_DATE_UNVERIFIED"),
            ({"classification-cpv":"48000000"},"CLASSIFICATION_MISMATCH"),
            ({"publication-date":"2026-11-25"},"PUBLICATION_OUTSIDE_WINDOW")]
        result=self.evaluate(Mock(return_value=(200,page([notice(i+1,**c) for i,(c,_) in enumerate(cases)]))))
        for _,reason in cases:
            self.assertTrue(any(reason in lead["blockers"] for lead in result["leads"]))
        self.assertFalse(any(lead["research_candidate"] for lead in result["leads"]))

    def test_language_fallback(self):
        raw=notice(**{"notice-title":{"fra":"Services informatiques","deu":"IT-Dienstleistungen"}})
        lead=self.evaluate(Mock(return_value=(200,page([raw]))))["leads"][0]
        self.assertEqual(lead["title_language"],"deu")
        self.assertEqual(lead["title"],"IT-Dienstleistungen")

    def test_pagination_cap(self):
        responses=[(200,page([notice(i+1) for i in range(n*PAGE_SIZE,(n+1)*PAGE_SIZE)],100)) for n in range(3)]
        transport=Mock(side_effect=responses)
        result=self.evaluate(transport)
        self.assertEqual(result["returned"],75)
        self.assertTrue(result["truncated"])
        self.assertEqual([c.args[0]["page"] for c in transport.call_args_list],[1,2,3])

    def test_retry_rate_limit_and_halt(self):
        transport=Mock(side_effect=[(503,b""),(200,page([]))])
        self.assertEqual(self.evaluate(transport)["requests"],2)
        transport=Mock(return_value=(429,b""))
        with self.assertRaisesRegex(SearchError,"TED_RATE_LIMIT_STOP"):
            self.evaluate(transport)
        self.assertEqual(transport.call_count,1)
        transport=Mock(return_value=(200,page([])))
        with self.assertRaises(PermissionError):
            self.evaluate(transport,halt_check=Mock(side_effect=[False,False,True]))
        self.assertEqual(transport.call_count,1)

    def test_duplicate_incomplete_and_timeout(self):
        for raw in (page([notice()],total=30),page([notice(),notice(**{"publication-number":"00000001-2026"})]),
                    page([],timedOut=True),b"{}",b" "*(MAX_BYTES+1),page([notice(**{"publication-number":"bad"})])):
            with self.subTest(length=len(raw)),self.assertRaises(SearchError):
                self.evaluate(Mock(return_value=(200,raw)))

    def test_empty_result_and_digest(self):
        result=self.evaluate(Mock(return_value=(200,page([]))))
        self.assertEqual(result["returned"],0)
        self.assertFalse(result["truncated"])
        self.assertEqual(len(result["page_sha256"][0]),64)

    def test_fixed_origin_no_redirect(self):
        with patch("nexus_exchange.ted_search.http.client.HTTPSConnection") as factory:
            conn=factory.return_value
            conn.getresponse.return_value.status=302
            self.assertEqual(_request(QUERY.parameters(NOW)),(302,b""))
            factory.assert_called_once_with(HOST,443,timeout=10)
            self.assertEqual(conn.request.call_args.args,("POST",PATH))
            self.assertNotIn("api_key",json.loads(conn.request.call_args.kwargs["body"]))
            conn.close.assert_called_once()
        for bad in ("../evil","https://evil.example","0-2026"):
            with self.assertRaises(ValueError):
                notice_url(bad)
