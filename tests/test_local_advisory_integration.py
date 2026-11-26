import copy
import json
import unittest
from datetime import timedelta

from nexus_exchange.local_advisory import build_request,review_response,_digest,TTL
from test_context_packet import snapshot,rehash,NOW

MODEL="d"*64


def wire(request,advice):
    return json.dumps(dict(format="nexus-local-advice-response-v1",
        request_sha256=request["request_sha256"],model_sha256=request["model_sha256"],
        advice=advice)).encode("ascii")


class LocalAdviceIntegrationTests(unittest.TestCase):
    def build(self,s,**overrides):
        opts=dict(now=NOW,approved=True,halted=False)
        opts.update(overrides)
        return build_request(s,MODEL,1,**opts)

    def review(self,raw,request,s,**overrides):
        opts=dict(now=NOW,approved=True,halted=False)
        opts.update(overrides)
        return review_response(raw,request,s,**opts)

    def test_real_council_projection_and_reference_bound_advice(self):
        s=snapshot(held=True,reference=True)
        request=self.build(s)
        self.assertEqual(request,self.build(s))
        self.assertEqual(request["snapshot_sha256"],s["snapshot_sha256"])
        self.assertEqual(request["source_hold"],s["source_hold"])
        self.assertNotIn("scenario",request)
        self.assertNotIn("context",request)
        field=request["fields"][0]
        self.assertEqual(field["reference_ids"],s["reference_ids"][field["field"]])
        advice=[dict(field=field["field"],reason=field["state"],reference_id=field["reference_ids"][0])]
        result=self.review(wire(request,advice),request,s)
        self.assertEqual(result["advice"],advice)
        self.assertEqual(result["source_hold"],"SOURCE_REVIEW_REQUIRED")
        self.assertFalse(result["external_authority"])
        self.assertFalse(result["execution_eligible"])
        self.assertFalse(result["independently_verified"])

    def test_omitted_advice_does_not_remove_unknown_or_missing_fields(self):
        s=snapshot()
        unknown=s["missing_reference_fields"][0]
        s["unknown_fields"]=[unknown]
        s["unknown"]=1
        rehash(s)
        request=self.build(s)
        states={item["field"]:item["state"] for item in request["fields"]}
        self.assertEqual(states[unknown],"UNKNOWN_ASSUMPTION")
        result=self.review(wire(request,[]),request,s)
        self.assertEqual(set(result["unresolved_fields"]),set(s["missing_reference_fields"]))

    def test_resealed_request_and_current_snapshot_drift_fail_closed(self):
        s=snapshot()
        request=self.build(s)
        altered=copy.deepcopy(request)
        altered["fields"][0]["state"]="REFERENCES_REQUIRE_VERIFICATION"
        altered["request_sha256"]=_digest({k:v for k,v in altered.items() if k!="request_sha256"})
        with self.assertRaises(ValueError):
            self.review(wire(altered,[]),altered,s)
        newer=snapshot(held=True)
        with self.assertRaises(ValueError):
            self.review(wire(request,[]),request,newer)

    def test_consent_halt_expiry_future_and_attempt_ceiling(self):
        s=snapshot()
        request=self.build(s)
        raw=wire(request,[])
        for opts in (dict(approved=False),dict(approved=1),dict(halted=True),dict(halted=None),dict(halted=0)):
            with self.subTest(opts=opts),self.assertRaises(PermissionError):
                self.build(s,**opts)
            with self.subTest(opts=opts),self.assertRaises(PermissionError):
                self.review(raw,request,s,**opts)
        for now in (NOW+TTL+timedelta(microseconds=1),NOW-timedelta(microseconds=1)):
            with self.assertRaises(ValueError):
                self.build(s,now=now)
            with self.assertRaises(ValueError):
                self.review(raw,request,s,now=now)
        for attempt in (True,0,4):
            with self.assertRaises(ValueError):
                build_request(s,MODEL,attempt,now=NOW,approved=True,halted=False)
        self.assertEqual(build_request(s,MODEL,3,now=NOW,approved=True,halted=False)["attempt"],3)


if __name__=="__main__":
    unittest.main()
