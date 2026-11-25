import json
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch
from nexus_exchange.governor import Action, decide, decide_sam_read
from nexus_exchange.sam_search import Query, search, SearchError, PAGE_SIZE, MAX_BYTES, _request, HOST, PATH

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
QUERY=Query(date(2026,11,10),date(2026,11,24),"document processing")
KEY="synthetic-test-key"

def notice(i=1,**kwargs):
    row=dict(noticeId=f"{i:032x}",title="Synthetic digital services",
        type="Combined Synopsis/Solicitation",active="Yes",postedDate="2026-11-20",
        responseDeadLine="2026-12-01T12:00:00Z",naicsCode="541519")
    row.update(kwargs)
    return row

def page(rows,total=None,offset=0):
    return json.dumps(dict(totalRecords=len(rows) if total is None else total,
        limit=PAGE_SIZE,offset=offset,opportunitiesData=rows)).encode()

class SamSearchTests(unittest.TestCase):
    def setUp(self):
        pacing=patch('nexus_exchange.sam_search.sleep')
        pacing.start()
        self.addCleanup(pacing.stop)

    def run_search(self, transport, **kw):
        args=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW,transport=transport)
        args.update(kw)
        return search(QUERY,KEY,**args)

    def test_consent_is_narrow_and_default_denied(self):
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)
        self.assertFalse(decide(Action.OUTREACH,halted=False).allowed)
        self.assertFalse(decide_sam_read(approved=True,halted=False).external_authority)
        for opts in (dict(approved=None),dict(approved=1),dict(halt_check=lambda:True),
                     dict(halt_check=lambda:None),dict(halt_check=lambda:0)):
            transport=Mock()
            with self.assertRaises(PermissionError):
                self.run_search(transport,**opts)
            transport.assert_not_called()

    def test_query_bounds(self):
        for q in (Query(date(2026,1,1),date(2026,11,24),"x"),
                  Query(date(2026,11,24),date(2026,11,25),"x"),
                  Query(date(2026,11,1),date(2026,11,24),"x","a"),
                  Query(date(2026,11,1),date(2026,11,24)," ")):
            transport=Mock()
            with self.assertRaises(ValueError):
                search(q,KEY,approved=True,halt_check=lambda:False,clock=lambda:NOW,transport=transport)
            transport.assert_not_called()

    def test_research_only_and_minimized_data(self):
        row=notice(pointOfContact=[{"email":"private@example.org"}],
                   award={"amount":"999999"},uiLink="https://evil.example/")
        transport=Mock(return_value=(200,page([row])))
        report=self.run_search(transport)
        lead=report["leads"][0]
        self.assertTrue(lead["research_candidate"])
        self.assertFalse(lead["execution_eligible"])
        self.assertIsNone(lead["cash_exposure"])
        self.assertEqual(len(lead["todo"]),7)
        self.assertTrue(all(t["notice_id"]==lead["notice_id"] and t["status"]=="needs independent evidence" for t in lead["todo"]))
        self.assertIn("COMPENSATION_UNVERIFIED",lead["blockers"])
        self.assertEqual(lead["source_url"],"https://sam.gov/opp/"+row["noticeId"]+"/view")
        serialized=json.dumps(report)
        for value in (KEY,"private@example.org","999999","evil.example"):
            self.assertNotIn(value,serialized)
        params,key=transport.call_args.args
        self.assertEqual(key,KEY)
        self.assertEqual(params["postedFrom"],"11/10/2026")
        self.assertEqual(params["offset"],0)
        self.assertNotIn("api_key",params)

    def test_notice_types_and_deadline(self):
        rows=[notice(1,type="Award Notice"),notice(2,active="No"),
              notice(3,responseDeadLine="2026-12-01T12:00:00"),
              notice(4,responseDeadLine="2026-11-23T12:00:00Z"),
              notice(5,postedDate="2026-11-25")]
        report=self.run_search(Mock(return_value=(200,page(rows))))
        self.assertTrue(all(not lead["research_candidate"] for lead in report["leads"]))
        for reason in ("NOT_SOLICITATION","ACTIVE_STATUS_UNCONFIRMED","DEADLINE_UNVERIFIED",
                       "DEADLINE_PASSED","FUTURE_POSTED_DATE"):
            self.assertTrue(any(reason in lead["blockers"] for lead in report["leads"]))

    def test_bounded_pagination(self):
        responses=[(200,page([notice(j+1) for j in range(i*PAGE_SIZE,(i+1)*PAGE_SIZE)],100,i)) for i in range(3)]
        transport=Mock(side_effect=responses)
        report=self.run_search(transport)
        self.assertEqual(report["returned"],75)
        self.assertEqual(report["requests"],3)
        self.assertTrue(report["truncated"])
        self.assertEqual([c.args[0]["offset"] for c in transport.call_args_list],[0,1,2])

    def test_retry_and_rate_limit(self):
        transport=Mock(side_effect=[(503,b""),(200,page([]))])
        self.assertEqual(self.run_search(transport)["requests"],2)
        transport=Mock(return_value=(429,b""))
        with self.assertRaisesRegex(SearchError,"SAM_RATE_LIMIT_STOP"):
            self.run_search(transport)
        self.assertEqual(transport.call_count,1)

    def test_halt_after_request(self):
        stop=Mock(side_effect=[False,False,True])
        transport=Mock(return_value=(200,page([notice()])))
        with self.assertRaises(PermissionError):
            self.run_search(transport,halt_check=stop)
        self.assertEqual(transport.call_count,1)

    def test_inconsistent_or_invalid_response(self):
        for raw in (b"{}",b" "* (MAX_BYTES+1),page([notice(1),notice(1)]),
                    page([notice()],total=26),page([notice(noticeId="invalid")]),
                    page([notice(title=KEY)])):
            with self.subTest(raw_length=len(raw)),self.assertRaises(SearchError):
                self.run_search(Mock(return_value=(200,raw)))

    def test_transport_failure_is_redacted(self):
        transport=Mock(side_effect=RuntimeError("request failed for "+KEY))
        with self.assertRaises(SearchError) as error:
            self.run_search(transport)
        self.assertNotIn(KEY,str(error.exception))

    def test_fixed_origin_no_redirect_following(self):
        with patch("nexus_exchange.sam_search.http.client.HTTPSConnection") as factory:
            connection=factory.return_value
            connection.getresponse.return_value.status=302
            self.assertEqual(_request({"title":"test&value"},KEY),(302,b""))
            factory.assert_called_once_with(HOST,443,timeout=10)
            method,path=connection.request.call_args.args
            self.assertEqual(method,"GET")
            self.assertTrue(path.startswith(PATH+"?"))
            self.assertIn("title=test%26value",path)
            self.assertEqual(connection.request.call_count,1)
            connection.close.assert_called_once()

    def test_empty_result_and_not_found_distinguished(self):
        report=self.run_search(Mock(return_value=(200,page([]))))
        self.assertEqual(report["leads"],[])
        self.assertFalse(report["truncated"])
        transport=Mock(return_value=(404,b""))
        with self.assertRaisesRegex(SearchError,"SAM_NO_DATA_OR_NOT_FOUND"):
            self.run_search(transport)
        self.assertEqual(transport.call_count,1)

    def test_encoded_secret_echo_rejected(self):
        raw=page([notice(title=KEY)]).replace(KEY.encode(),b"synthetic-test-\\u006bey")
        self.assertNotIn(KEY.encode(),raw)
        with self.assertRaisesRegex(SearchError,"SAM_REPORT_CONTAINS_CREDENTIAL"):
            self.run_search(Mock(return_value=(200,raw)))
