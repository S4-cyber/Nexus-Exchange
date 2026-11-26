import json
import unittest

from nexus_exchange.local_advisory import _parse_advice, MAX_RESPONSE_BYTES


def request():
    return dict(request_sha256="a"*64, model_sha256="b"*64,
                source_hold="SOURCE_REVIEW_REQUIRED", fields=[
                    dict(field="cost:fixture",state="MISSING_REFERENCE",reference_ids=[]),
                    dict(field="schedule:fixture",state="UNKNOWN_ASSUMPTION",reference_ids=[]),
                    dict(field="price",state="REFERENCES_REQUIRE_VERIFICATION",reference_ids=["c"*64])])


def response(**changes):
    data=dict(format="nexus-local-advice-response-v1",request_sha256="a"*64,
              model_sha256="b"*64,advice=[dict(field="price",reason="REFERENCES_REQUIRE_VERIFICATION",reference_id="c"*64)])
    data.update(changes)
    return json.dumps(data).encode("ascii")


class LocalAdviceParserTests(unittest.TestCase):
    def test_bound_reference_remains_unverified_and_holds_preserved(self):
        result=_parse_advice(response(),request())
        self.assertEqual(result["advice"][0]["reference_id"],"c"*64)
        self.assertEqual(result["source_hold"],"SOURCE_REVIEW_REQUIRED")
        self.assertEqual(result["unresolved_fields"],["cost:fixture","schedule:fixture"])
        for flag in ("independently_verified","execution_eligible","external_authority","dispatch_enabled"):
            self.assertIs(result[flag],False)

    def test_request_and_model_mismatch_rejected(self):
        for changes in (dict(request_sha256="d"*64),dict(model_sha256="d"*64)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                _parse_advice(response(**changes),request())

    def test_cross_field_reference_and_fabricated_evidence_rejected(self):
        for item in (dict(field="price",reason="REFERENCES_REQUIRE_VERIFICATION",reference_id="d"*64),
                     dict(field="cost:fixture",reason="MISSING_REFERENCE",reference_id="c"*64),
                     dict(field="other",reason="UNKNOWN_ASSUMPTION",reference_id=None),
                     dict(field="schedule:fixture",reason="MISSING_REFERENCE",reference_id=None)):
            with self.subTest(item=item),self.assertRaises(ValueError):
                _parse_advice(response(advice=[item]),request())

    def test_authority_and_command_fields_never_accepted(self):
        for raw in (response(approved=True),response(external_authority=False),
                    response(advice=[dict(field="price",reason="EXECUTE",reference_id="c"*64)]),
                    response(advice=[dict(field="price",reason="REFERENCES_REQUIRE_VERIFICATION",reference_id="c"*64,command="run")])):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                _parse_advice(raw,request())

    def test_duplicate_and_bounded_output_rejected(self):
        item=dict(field="cost:fixture",reason="MISSING_REFERENCE",reference_id=None)
        for raw in (response(advice=[item,item]), b'{"a":1,"a":2}',b'{"x":NaN}',b'x'*(MAX_RESPONSE_BYTES+1),b'\xff'):
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):
                _parse_advice(raw,request())
        empty=_parse_advice(response(advice=[]),request())
        self.assertEqual(empty["advice"],[])
        self.assertFalse(empty["execution_eligible"])


if __name__=="__main__":
    unittest.main()
