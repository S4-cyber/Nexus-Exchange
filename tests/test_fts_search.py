import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from nexus_exchange.governor import Action, decide, decide_fts_read
from nexus_exchange.fts_search import (FtsQuery,search,notice_url,_request,
    HOST,PATH,PAGE_SIZE,MAX_BYTES,SearchError)

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
QUERY=FtsQuery(NOW-timedelta(days=1),NOW)

def release(i=1,**changes):
    row=dict(ocid=f"ocds-h6vhtk-test-{i}",id=f"{i:06d}-2026",
        date="2026-11-24T09:00:00Z",tag=["tender"],initiationType="tender",
        tender=dict(title="Synthetic digital service",status="active",
            tenderPeriod=dict(endDate="2026-12-02T12:00:00Z")))
    row.update(changes)
    return row

def page(rows,cursor=None,**changes):
    data=dict(version="1.1",releases=rows)
    if cursor is not None:
        data["links"]={"next":"https://"+HOST+PATH+"?"+urlencode({"cursor":cursor})}
    data.update(changes)
    return json.dumps(data).encode()

class FtsTests(unittest.TestCase):
    def setUp(self):
        pacing=patch("nexus_exchange.fts_search.sleep")
        pacing.start()
        self.addCleanup(pacing.stop)

    def evaluate(self,transport,**changes):
        opts=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW,transport=transport)
        opts.update(changes)
        return search(QUERY,**opts)

    def test_scope_and_halt(self):
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)
        self.assertFalse(decide(Action.BID,halted=False).allowed)
        self.assertFalse(decide_fts_read(approved=True,halted=False).external_authority)
        for changes in (dict(approved=None),dict(approved=1),dict(halt_check=lambda:True),
                        dict(halt_check=lambda:None)):
            transport=Mock()
            with self.assertRaises(PermissionError):
                self.evaluate(transport,**changes)
            transport.assert_not_called()

    def test_frozen_window(self):
        params=QUERY.parameters(NOW)
        self.assertEqual(params,dict(updatedFrom="2026-11-23T12:00:00",
            updatedTo="2026-11-24T12:00:00",limit="25"))
        self.assertNotIn("stages",params)
        for start,end in ((NOW-timedelta(days=8),NOW),(NOW,NOW),(NOW,NOW+timedelta(days=1)),
                          (NOW.replace(tzinfo=None),NOW)):
            with self.assertRaises(ValueError):
                FtsQuery(start,end).parameters(NOW)

    def test_research_only_data_minimized(self):
        raw=release(parties=[{"contactPoint":{"email":"private@example.org"}}],
            awards=[{"value":{"amount":999999}}])
        report=self.evaluate(Mock(return_value=(200,page([raw]))))
        lead=report["leads"][0]
        self.assertTrue(lead["research_candidate"])
        self.assertFalse(lead["execution_eligible"])
        self.assertFalse(lead["external_authority"])
        self.assertIsNone(lead["cash_exposure"])
        self.assertIn("CURRENT_TENDER_STATE_UNVERIFIED",lead["blockers"])
        self.assertEqual(lead["source_url"],"https://"+HOST+"/Notice/000001-2026")
        self.assertEqual(len(lead["todo"]),7)
        for value in ("private@example.org","999999"):
            self.assertNotIn(value,json.dumps(report))

    def test_lifecycle_blocks_old_tender_even_without_new_tender_fields(self):
        first=release()
        award=release(2,ocid=first["ocid"],date="2026-11-24T10:00:00Z",
            tag=["award"],tender=None)
        report=self.evaluate(Mock(side_effect=[(200,page([first],"abc")),(200,page([award]))]))
        rows={r["notice_id"]:r for r in report["leads"]}
        self.assertFalse(any(r["research_candidate"] for r in rows.values()))
        self.assertIn("SUPERSEDED_WITHIN_COLLECTED_WINDOW",rows[first["id"]]["blockers"])
        self.assertIn("NOT_SUPPORTED_TENDER_EVENT",rows[award["id"]]["blockers"])

    def test_equal_timestamp_ambiguous(self):
        first=release()
        second=release(2,ocid=first["ocid"])
        report=self.evaluate(Mock(return_value=(200,page([first,second]))))
        self.assertTrue(all("AMBIGUOUS_LATEST_RELEASE" in r["blockers"] for r in report["leads"]))

    def test_invalid_deadlines_and_status(self):
        rows=[release(1,tender=dict(title="No deadline",status="active")),
              release(2,tender=dict(title="Expired",status="active",tenderPeriod=dict(endDate="2026-11-23T00:00:00Z"))),
              release(3,tender=dict(title="Cancelled",status="cancelled")),
              release(4,date="2026-11-25T00:00:00Z")]
        result=self.evaluate(Mock(return_value=(200,page(rows))))
        self.assertFalse(any(r["research_candidate"] for r in result["leads"]))
        for reason in ("REPORTED_DEADLINE_UNVERIFIED","REPORTED_DEADLINE_PASSED",
                       "ACTIVE_STATUS_UNCONFIRMED","FUTURE_RELEASE"):
            self.assertTrue(any(reason in r["blockers"] for r in result["leads"]))

    def test_cursor_frozen_and_deduplicated(self):
        first=release()
        transport=Mock(side_effect=[(200,page([first],"a+b=")),(200,page([first,release(2)]))])
        report=self.evaluate(transport)
        self.assertEqual(report["returned"],2)
        self.assertFalse(report["truncated"])
        self.assertEqual(transport.call_args_list[1].args[0],dict(QUERY.parameters(NOW),cursor="a+b="))
        self.assertEqual(len(report["page_sha256"]),2)

    def test_foreign_cursor_and_changed_params_rejected(self):
        for url in ("https://evil.example"+PATH+"?cursor=a",
                    "https://"+HOST+"/other?cursor=a",
                    PATH+"?cursor=a&updatedFrom=2000-01-01T00:00:00",
                    PATH+"?cursor=a&cursor=b",PATH+"?cursor=a#fragment"):
            transport=Mock(return_value=(200,page([release()],links={"next":url})))
            with self.subTest(url=url),self.assertRaises(SearchError):
                self.evaluate(transport)
            self.assertEqual(transport.call_count,1)

    def test_cap_blocks_all_incomplete_window_candidates(self):
        transport=Mock(side_effect=[(200,page([release(i)],str(i))) for i in (1,2,3)])
        report=self.evaluate(transport)
        self.assertEqual(report["requests"],3)
        self.assertTrue(report["truncated"])
        self.assertTrue(all(not r["research_candidate"] and "COLLECTION_WINDOW_INCOMPLETE" in r["blockers"]
            for r in report["leads"]))

    def test_conflicting_duplicate_and_cycle_rejected(self):
        first=release()
        changed=release(tender=dict(title="Changed",status="active"))
        for responses in ([(200,page([first],"x")),(200,page([changed]))],
                          [(200,page([first],"x")),(200,page([release(2)],"x"))]):
            with self.assertRaises(SearchError):
                self.evaluate(Mock(side_effect=responses))

    def test_invalid_packages(self):
        for raw in (b"{}",page([],version="2.0"),page([release() for _ in range(PAGE_SIZE+1)]),
                    b" "*(MAX_BYTES+1),page([release(id="invalid")]),
                    page([release(tag=["tender","tender"])])):
            with self.subTest(length=len(raw)),self.assertRaises(SearchError):
                self.evaluate(Mock(return_value=(200,raw)))

    def test_retry_rate_limit_and_halt(self):
        transport=Mock(side_effect=[(503,b""),(200,page([]))])
        self.assertEqual(self.evaluate(transport)["requests"],2)
        transport=Mock(return_value=(429,b""))
        with self.assertRaisesRegex(SearchError,"FTS_RATE_LIMIT_STOP"):
            self.evaluate(transport)
        self.assertEqual(transport.call_count,1)
        transport=Mock(return_value=(200,page([])))
        with self.assertRaises(PermissionError):
            self.evaluate(transport,halt_check=Mock(side_effect=[False,False,True]))
        self.assertEqual(transport.call_count,1)

    def test_fixed_origin_and_no_redirect(self):
        from urllib.error import HTTPError
        from nexus_exchange.public_feeds import NoRedirect
        with patch("nexus_exchange.public_feeds.build_opener") as factory:
            transport = factory.return_value.open
            transport.side_effect = HTTPError("https://" + HOST, 302, "redirect", {}, None)
            self.assertEqual(_request(QUERY.parameters(NOW)), (302,b""))
            request = transport.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url.split("?")[0], "https://" + HOST + PATH)
            self.assertIsInstance(factory.call_args.args[0], NoRedirect)
            self.assertIsNone(NoRedirect().redirect_request(request, None, 302, "", {}, "https://elsewhere.invalid"))
            transport.assert_called_once()
        for bad in ("../evil","https://evil.example","000000-2026"):
            with self.assertRaises(ValueError):
                notice_url(bad)
