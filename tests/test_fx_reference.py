import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from nexus_exchange.fx_reference import (
    FxError, MAX_BYTES, fetch_reference, parse_reference, source_url,
)
from nexus_exchange.governor import Action, decide, decide_fx_read

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
RAW=b'{"date":"2026-11-23","base":"EUR","quote":"USD","rate":1.125}'


class FxReferenceTests(unittest.TestCase):
    def parse(self,raw=RAW,amount="100.04",base="EUR",**kwargs):
        return parse_reference(raw,base,amount,**(dict(now=NOW,halted=False)|kwargs))

    def test_exact_decimal_with_half_even_display(self):
        result=self.parse()
        self.assertEqual(result["indicative_usd_unrounded"],"112.54500")
        self.assertEqual(result["indicative_usd"],"112.54")
        self.assertEqual(result["age_days"],1)
        self.assertEqual(result["source_url"],"https://api.frankfurter.dev/v2/rate/EUR/USD")
        self.assertEqual(len(result["raw_sha256"]),64)
        for key in ("external_authority","execution_eligible","fees_included",
                    "settlement_rate","zero_capital_verified","independently_verified"):
            self.assertIs(result[key],False)

    def test_stale_future_and_wrong_pair(self):
        for raw in (RAW.replace(b"2026-11-23",b"2026-11-16"),
                    RAW.replace(b"2026-11-23",b"2026-11-25"),
                    RAW.replace(b'"EUR"',b'"CAD"'),RAW.replace(b'"USD"',b'"JPY"')):
            with self.subTest(raw=raw),self.assertRaises(FxError):
                self.parse(raw)

    def test_invalid_schema_and_numbers(self):
        for raw in (b'{}',RAW.replace(b"1.125",b"true"),
                    RAW.replace(b"1.125",b"NaN"),RAW.replace(b"1.125",b"0"),
                    RAW.replace(b"1.125",b"-1"),RAW.replace(b"1.125",b'"1.125"'),
                    RAW.replace(b"1.125",b"1e9999"),
                    RAW.replace(b'"rate":',b'"rate":1,"rate":'),
                    RAW[:-1]+b',"instruction":"send money"}',
                    b"x"*(MAX_BYTES+1)):
            with self.subTest(raw=raw[:80]),self.assertRaises(FxError):
                self.parse(raw)

    def test_input_bounds_and_fixed_currency(self):
        for amount in ("-1","1e2","1,000","1.00001","1234567890123",True):
            with self.subTest(amount=amount),self.assertRaises(ValueError):
                self.parse(amount=amount)
        for base in ("USD","eur","EUR/../../","EUR?token=secret",None):
            with self.subTest(base=base),self.assertRaises(ValueError):
                source_url(base)

    def test_one_get_only_and_no_amount_sent(self):
        calls=[]
        def transport(base):
            calls.append(base)
            return 200,RAW
        result=fetch_reference("EUR","543.21",approved=True,halt_check=lambda:False,
                               transport=transport,clock=lambda:NOW)
        self.assertEqual(calls,["EUR"])
        self.assertEqual(result["requests"],1)
        self.assertFalse(result["authenticated_origin"])
        self.assertFalse(decide(Action.FETCH_EXTERNAL,halted=False).allowed)

    def test_consent_and_halt_before_transport(self):
        with patch("nexus_exchange.fx_reference._request") as request:
            for approved,state in ((None,False),(1,False),(True,None),(True,True),(True,0)):
                with self.subTest(approved=approved,state=state),self.assertRaises(PermissionError):
                    fetch_reference("EUR","1",approved=approved,halt_check=lambda:state)
            request.assert_not_called()
        self.assertFalse(decide_fx_read(approved=True,halted=False).external_authority)

    def test_halt_during_response_suppresses_output(self):
        state=False
        def transport(base):
            nonlocal state
            state=True
            return 200,RAW
        with self.assertRaises(PermissionError):
            fetch_reference("EUR","1",approved=True,halt_check=lambda:state,
                            transport=transport,clock=lambda:NOW)

    def test_status_failures_no_retry(self):
        for status in (301,302,429,500,True):
            with self.subTest(status=status),patch("nexus_exchange.fx_reference._request",return_value=(status,RAW)) as req:
                with self.assertRaises(FxError):
                    fetch_reference("EUR","1",approved=True,halt_check=lambda:False,clock=lambda:NOW)
                req.assert_called_once_with("EUR")

    def test_backward_clock_rejected(self):
        clock=iter([NOW,NOW-timedelta(seconds=1)]).__next__
        with self.assertRaises(FxError):
            fetch_reference("EUR","1",approved=True,halt_check=lambda:False,
                            transport=lambda base:(200,RAW),clock=clock)

    def test_http_transport_fixed_no_redirect_and_bounded(self):
        with patch("nexus_exchange.fx_reference.http.client.HTTPSConnection") as factory:
            connection=factory.return_value
            response=connection.getresponse.return_value
            response.status=200
            response.getheader.side_effect=lambda name,default=None: {
                "Content-Type":"application/json","Content-Encoding":"identity"}.get(name,default)
            response.read.return_value=RAW
            result=fetch_reference("EUR","1",approved=True,halt_check=lambda:False,clock=lambda:NOW)
            self.assertEqual(result["indicative_usd"],"1.12")
            factory.assert_called_once_with("api.frankfurter.dev",443,timeout=8)
            self.assertEqual(connection.request.call_args.args,("GET","/v2/rate/EUR/USD"))
            response.read.assert_called_once_with(MAX_BYTES+1)
            connection.close.assert_called_once()

    def test_http_transport_rejects_media_and_oversize(self):
        for media,body in (("text/html",RAW),("application/json",b"x"*(MAX_BYTES+1))):
            with patch("nexus_exchange.fx_reference.http.client.HTTPSConnection") as factory:
                response=factory.return_value.getresponse.return_value
                response.status=200
                response.getheader.side_effect=lambda name,default=None: {
                    "Content-Type":media,"Content-Encoding":"identity"}.get(name,default)
                response.read.return_value=body
                with self.assertRaises(FxError):
                    fetch_reference("EUR","1",approved=True,halt_check=lambda:False,clock=lambda:NOW)
                factory.return_value.close.assert_called_once()

if __name__=="__main__":
    unittest.main()
