import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from nexus_exchange.governor import Action, decide, decide_sec_read
from nexus_exchange.sec_company import (MAX_BYTES, MAX_DISPLAY, SecError,
    fetch_company, normalize_cik, parse_company, source_url)


NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
CIK="0000000123"
ORG="Synthetic Test LLC"
EMAIL="research@example.test"


def fixture():
    return dict(cik="123",entityType="operating",name="EXAMPLE INDUSTRIES INC",
        sic="7372",sicDescription="Software",tickers=["EXM"],
        addresses={"business":{"street1":"private-not-projected"}},
        phone="private-not-projected",filings=dict(recent=dict(
            accessionNumber=["0000000123-26-000002","0000000123-26-000001"],
            filingDate=["2026-11-23","2026-10-01"],form=["8-K","10-Q"],
            primaryDocument=["https://evil.example/secret","untrusted.htm"]),
            files=[{"name":"untrusted.json"}]))


def encoded(data):
    return json.dumps(data).encode("utf-8")


class SecCompanyTests(unittest.TestCase):
    def parse(self,data=None,**kwargs):
        return parse_company(encoded(fixture() if data is None else data),"123",
                             **(dict(now=NOW,halted=False)|kwargs))

    def fetch(self,**kwargs):
        return fetch_company("123",ORG,EMAIL,**(dict(approved=True,
            halt_check=lambda:False,clock=lambda:NOW)|kwargs))

    def test_normalized_cik_and_fixed_source(self):
        self.assertEqual(normalize_cik("123"),CIK)
        self.assertEqual(source_url("123"),"https://data.sec.gov/submissions/CIK0000000123.json")
        for bad in ("0","0000000000","12345678901","１２３","123/../../",
                    "https://example.com"," 123",123,True,None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                normalize_cik(bad)

    def test_company_projection_no_clearance_or_untrusted_urls(self):
        result=self.parse(expected_name="example industries inc")
        self.assertEqual(result["cik"],CIK)
        self.assertEqual(result["name_comparison"],"EXACT_CASEFOLD_MATCH")
        self.assertEqual(result["filings"][0]["source_url"],
            "https://www.sec.gov/Archives/edgar/data/123/000000012326000002/0000000123-26-000002-index.html")
        for key in ("identity_verified","capacity_verified","solvency_verified",
                    "contact_permission","external_authority","execution_eligible",
                    "independently_verified","filing_history_complete","zero_capital_verified"):
            self.assertIs(result[key],False)
        self.assertNotIn("private-not-projected",repr(result))
        self.assertNotIn("evil.example",repr(result))
        self.assertNotIn("untrusted.json",repr(result))

    def test_name_mismatch_is_not_silent(self):
        result=self.parse(expected_name="Different LLC")
        self.assertEqual(result["name_comparison"],"MISMATCH")
        self.assertIn("DECLARED_NAME_MISMATCH",result["reasons"])
        self.assertEqual(self.parse()["name_comparison"],"NOT_SUPPLIED")

    def test_cik_mismatch_and_nonoperating_entities(self):
        for change in (dict(cik="124"),dict(cik=True),dict(entityType="other"),
                       dict(entityType="individual"),dict(entityType=None)):
            with self.subTest(change=change),self.assertRaises(SecError):
                self.parse(dict(fixture(),**change))

    def test_malformed_filing_columns_and_future_dates(self):
        for key,value in (("accessionNumber",["https://example.com"]),
                          ("accessionNumber",["0000000123-26-000001"]*2),
                          ("filingDate",["2026-11-25","2026-10-01"]),
                          ("form",["8-K"]),("form",[False,"10-Q"])):
            data=fixture()
            data["filings"]["recent"][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(SecError):
                self.parse(data)

    def test_bounded_display_and_no_nonselected_forms(self):
        data=fixture()
        n=MAX_DISPLAY+2
        data["filings"]["recent"]=dict(
            accessionNumber=["0000000123-26-%06d"%i for i in range(n+1)],
            filingDate=["2026-11-23"]*(n+1),form=["8-K"]*n+["4"])
        result=self.parse(data)
        self.assertEqual(result["recent_rows_observed"],n+1)
        self.assertEqual(result["selected_forms_observed"],n)
        self.assertEqual(len(result["filings"]),MAX_DISPLAY)
        self.assertTrue(result["display_truncated"])

    def test_invalid_json_controls_and_size(self):
        for raw in (b'{"cik":"123","cik":"124"}',b'{"cik":NaN}',
                    b"x"*(MAX_BYTES+1),encoded(dict(fixture(),name="BAD\u202eNAME"))):
            with self.subTest(raw=raw[:80]),self.assertRaises(SecError):
                parse_company(raw,"123",now=NOW,halted=False)

    def test_consent_contact_and_halt_before_transport(self):
        with patch("nexus_exchange.sec_company._request") as request:
            for approved,state in ((None,False),(1,False),(True,None),(True,True),(True,0)):
                with self.assertRaises(PermissionError):
                    self.fetch(approved=approved,halt_check=lambda:state)
            for org,email in (("","research@example.test"),("Bad\r\nHeader",EMAIL),
                              (ORG,"bad\r\n@example.test"),(ORG,"not-email")):
                with self.assertRaises(ValueError):
                    fetch_company("123",org,email,approved=True,halt_check=lambda:False)
            request.assert_not_called()
        self.assertFalse(decide_sec_read(approved=True,halted=False).external_authority)
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)

    def test_one_request_contact_not_in_report(self):
        with patch("nexus_exchange.sec_company._request",return_value=(200,encoded(fixture()))) as request:
            result=self.fetch(expected_name="Example Industries Inc")
            request.assert_called_once_with(CIK,"NexusExchange-Preview/1 "+ORG+" "+EMAIL)
            self.assertEqual(result["requests"],1)
            self.assertNotIn(EMAIL,repr(result))
            self.assertNotIn(ORG,repr(result))

    def test_halt_during_response_and_backward_clock(self):
        halted=False
        def transport(cik,agent):
            nonlocal halted
            halted=True
            return 200,encoded(fixture())
        with self.assertRaises(PermissionError):
            self.fetch(transport=transport,halt_check=lambda:halted)
        clock=iter([NOW,NOW-timedelta(seconds=1)]).__next__
        with self.assertRaises(SecError):
            self.fetch(transport=lambda *args:(200,encoded(fixture())),clock=clock)

    def test_no_retry_or_redirect_follow(self):
        for status in (301,302,403,404,429,500,True):
            with patch("nexus_exchange.sec_company._request",return_value=(status,b"")) as request:
                with self.assertRaises(SecError):
                    self.fetch()
                request.assert_called_once()

    def test_fixed_transport_and_process_rate_gate(self):
        with patch("nexus_exchange.sec_company._LAST_REQUEST_NS",None), \
             patch("nexus_exchange.sec_company.monotonic_ns",side_effect=[1,2]), \
             patch("nexus_exchange.sec_company.http.client.HTTPSConnection") as factory:
            conn=factory.return_value
            response=conn.getresponse.return_value
            response.status=200
            response.getheader.side_effect=lambda name,default=None: {
                "Content-Type":"application/json","Content-Encoding":"identity"}.get(name,default)
            response.read.return_value=encoded(fixture())
            self.fetch()
            with self.assertRaisesRegex(SecError,"SEC_LOCAL_RATE_LIMIT"):
                self.fetch()
            factory.assert_called_once_with("data.sec.gov",443,timeout=10)
            self.assertEqual(conn.request.call_args.args,
                             ("GET","/submissions/CIK"+CIK+".json"))
            response.read.assert_called_once_with(MAX_BYTES+1)
            conn.close.assert_called_once()

    def test_http_media_and_size_validation(self):
        for media,body in (("text/html",b"html"),("application/json",b"x"*(MAX_BYTES+1))):
            with patch("nexus_exchange.sec_company._LAST_REQUEST_NS",None), \
                 patch("nexus_exchange.sec_company.http.client.HTTPSConnection") as factory:
                response=factory.return_value.getresponse.return_value
                response.status=200
                response.getheader.side_effect=lambda name,default=None: {
                    "Content-Type":media,"Content-Encoding":"identity"}.get(name,default)
                response.read.return_value=body
                with self.assertRaises(SecError):
                    self.fetch()
                factory.return_value.close.assert_called_once()

if __name__=="__main__":
    unittest.main()
