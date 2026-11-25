import csv
import io
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock,patch
from nexus_exchange.governor import Action,decide,decide_canada_read
from nexus_exchange.canada_search import (CanadaQuery,search,notice_url,_request,HOST,PATH,
    MAX_BYTES,MAX_RESULTS,REFERENCE,TITLE,FRENCH_TITLE,PUBLICATION,CLOSING,NOTICE_TYPE,STATUS_FIELDS,SearchError)

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
MODIFIED="Tue, 24 Nov 2026 10:00:00 GMT"
QUERY=CanadaQuery("software")
HEADER=[REFERENCE,TITLE,FRENCH_TITLE,PUBLICATION,CLOSING,NOTICE_TYPE,STATUS_FIELDS[0],"contactInfoEmail-informationsContactCourriel"]

def notice(i=1,**changes):
    row={REFERENCE:f"cb-{i}",TITLE:"Synthetic software service",FRENCH_TITLE:"Service logiciel",
        PUBLICATION:"2026-11-20",CLOSING:"2026-12-01T13:00:00",NOTICE_TYPE:"Request for Proposal",
        STATUS_FIELDS[0]:"Open","contactInfoEmail-informationsContactCourriel":"private@example.org"}
    row.update(changes)
    return row

def dataset(rows,header=HEADER):
    buffer=io.StringIO(newline="")
    writer=csv.writer(buffer)
    writer.writerow(header)
    writer.writerows([row.get(field,"") for field in header] for row in rows)
    return buffer.getvalue().encode("utf-8-sig")

class CanadaTests(unittest.TestCase):
    def evaluate(self,rows=None,raw=None,modified=MODIFIED,**kw):
        transport=Mock(return_value=(200,dataset(rows or []) if raw is None else raw,modified))
        args=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW,transport=transport)
        args.update(kw)
        return search(QUERY,**args)

    def test_consent_precedes_request(self):
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)
        self.assertFalse(decide(Action.BID,halted=False).allowed)
        self.assertFalse(decide_canada_read(approved=True,halted=False).external_authority)
        for changes in (dict(approved=None),dict(approved=1),dict(halt_check=lambda:True),
                        dict(halt_check=lambda:None)):
            transport=Mock()
            with self.assertRaises(PermissionError):
                self.evaluate(transport=transport,**changes)
            transport.assert_not_called()

    def test_bounded_title_query(self):
        for value in ("a"," "*4,"x"*121,"ab\ncd"):
            with self.assertRaises(ValueError):
                CanadaQuery(value).validated()
        self.assertEqual(CanadaQuery(" Software ").validated(),"software")

    def test_open_notice_and_minimized_evidence(self):
        report=self.evaluate([notice()])
        lead=report["leads"][0]
        self.assertTrue(lead["research_candidate"])
        self.assertFalse(lead["execution_eligible"])
        self.assertFalse(lead["external_authority"])
        self.assertIsNone(lead["cash_exposure"])
        self.assertIsNone(lead["deadline"])
        self.assertEqual(lead["reported_closing"],"2026-12-01T13:00:00")
        self.assertIn("EXACT_DEADLINE_TIMEZONE_UNVERIFIED",lead["blockers"])
        self.assertNotIn("private@example.org",str(report))
        self.assertEqual(len(lead["todo"]),7)
        self.assertEqual(len(report["page_sha256"][0]),64)
        self.assertEqual(report["source_row_count"],1)

    def test_timezone_aware_deadline(self):
        lead=self.evaluate([notice(**{CLOSING:"2026-12-01T13:00:00-05:00"})])["leads"][0]
        self.assertEqual(lead["deadline"],"2026-12-01T18:00:00+00:00")
        self.assertNotIn("EXACT_DEADLINE_TIMEZONE_UNVERIFIED",lead["blockers"])

    def test_freshness_fail_closed(self):
        for modified,reason in ((None,"DATASET_FRESHNESS_UNVERIFIED"),
              ("Fri, 20 Nov 2026 10:00:00 GMT","DATASET_STALE"),
              ("Wed, 25 Nov 2026 10:00:00 GMT","DATASET_TIMESTAMP_IN_FUTURE")):
            lead=self.evaluate([notice()],modified=modified)["leads"][0]
            self.assertFalse(lead["research_candidate"])
            self.assertIn(reason,lead["blockers"])

    def test_notice_status_type_and_deadline(self):
        cases=[({STATUS_FIELDS[0]:"Expired"},"NOT_OPEN"),
            ({NOTICE_TYPE:"Request for Information"},"NOTICE_TYPE_REQUIRES_REVIEW"),
            ({CLOSING:"2026-11-24T20:00:00"},"REPORTED_DEADLINE_PASSED_OR_TODAY"),
            ({CLOSING:"invalid"},"REPORTED_DEADLINE_UNVERIFIED"),
            ({PUBLICATION:"2026-11-25"},"FUTURE_PUBLICATION")]
        result=self.evaluate([notice(i+1,**changes) for i,(changes,_) in enumerate(cases)])
        self.assertFalse(any(row["research_candidate"] for row in result["leads"]))
        for _,reason in cases:
            self.assertTrue(any(reason in row["blockers"] for row in result["leads"]))

    def test_full_scan_and_output_cap(self):
        rows=[notice(i+1) for i in range(MAX_RESULTS+3)]
        rows.append(notice(900,**{TITLE:"Unrelated hardware",FRENCH_TITLE:"Matériel"}))
        result=self.evaluate(rows)
        self.assertEqual(result["source_row_count"],MAX_RESULTS+4)
        self.assertEqual(result["reported_total"],MAX_RESULTS+3)
        self.assertEqual(result["returned"],MAX_RESULTS)
        self.assertTrue(result["truncated"])

    def test_bilingual_title_and_legacy_link(self):
        row=notice(**{REFERENCE:"PW-123",TITLE:"",FRENCH_TITLE:"Software logiciel"})
        lead=self.evaluate([row])["leads"][0]
        self.assertEqual(lead["title_language"],"fra")
        self.assertIn("DIRECT_NOTICE_LINK_UNVERIFIED",lead["blockers"])
        self.assertEqual(lead["source_url"],"https://"+HOST+"/en/tender-opportunities")
        self.assertEqual(notice_url("cb-123"),"https://"+HOST+"/en/tender-opportunities/tender-notice/cb-123")

    def test_status_alias_and_schema_drift(self):
        header=[STATUS_FIELDS[1] if h==STATUS_FIELDS[0] else h for h in HEADER]
        row=notice(**{STATUS_FIELDS[1]:"Open"})
        self.assertTrue(self.evaluate(raw=dataset([row],header))["leads"][0]["research_candidate"])
        for h in (HEADER[:-2],HEADER+[STATUS_FIELDS[1]],HEADER+[TITLE]):
            with self.assertRaises(SearchError):
                self.evaluate(raw=dataset([row],h))

    def test_duplicates_and_malformed_rows(self):
        for raw in (dataset([notice(),notice()]),dataset([notice()])+b"short,row\n",
                    b"not a CSV",b" "*(MAX_BYTES+1),dataset([notice(**{REFERENCE:"../bad"})])):
            with self.assertRaises(SearchError):
                self.evaluate(raw=raw)

    def test_rate_limit_access_and_halt(self):
        for status in (403,429,503):
            transport=Mock(return_value=(status,b"",None))
            with self.assertRaises(SearchError):
                self.evaluate(transport=transport)
            self.assertEqual(transport.call_count,1)
        transport=Mock(return_value=(200,dataset([notice()]),MODIFIED))
        with self.assertRaises(PermissionError):
            self.evaluate(transport=transport,halt_check=Mock(side_effect=[False,True]))

    def test_fixed_origin_no_redirect(self):
        from urllib.error import HTTPError
        from nexus_exchange.public_feeds import NoRedirect
        with patch("nexus_exchange.public_feeds.build_opener") as factory:
            transport = factory.return_value.open
            transport.side_effect = HTTPError("https://" + HOST, 302, "redirect", {}, None)
            self.assertEqual(_request(), (302,b"",None))
            request = transport.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url.split("?")[0], "https://" + HOST + PATH)
            self.assertIsInstance(factory.call_args.args[0], NoRedirect)
            self.assertIsNone(NoRedirect().redirect_request(request, None, 302, "", {}, "https://elsewhere.invalid"))
            transport.assert_called_once()
        self.assertEqual(notice_url("SSC-26-00035538:T"), "https://" + HOST + "/en/tender-opportunities")
        for bad in ("SSC-26-00035538:../T", "../bad","https://evil.example","a/b"):
            with self.assertRaises(ValueError):
                notice_url(bad)
