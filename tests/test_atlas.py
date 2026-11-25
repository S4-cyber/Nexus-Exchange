import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from nexus_exchange.atlas import normalize_party, qualify_suppliers
from nexus_exchange.scout import normalize

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
CODE = ("CPV", "30200000")
REGION = "US-CA"

def party(role, ident, **overrides):
    raw = dict(scheme="EXAMPLE", identifier=ident, name="Synthetic " + role,
        roles=[role], classifications=[dict(scheme=CODE[0], code=CODE[1])],
        regions=[REGION], currency="USD", capacity="2000",
        source_url="https://example.org/registry", observed_at=NOW.isoformat())
    raw.update(overrides)
    return raw

def opportunity(**overrides):
    raw = dict(source="example",external_id="tender-1",title="Synthetic procurement",
        source_url="https://example.org/tender",retrieved_at=NOW.isoformat(),
        deadline="2026-12-01T12:00:00Z",currency="USD",amount="1000")
    raw.update(overrides)
    return normalize(raw)

class AtlasTests(unittest.TestCase):
    def match(self, suppliers, buyer=None, op=None, **overrides):
        args=dict(classifications=[dict(scheme=CODE[0],code=CODE[1])],
            region=REGION,now=NOW,halted=False)
        args.update(overrides)
        return qualify_suppliers(op if op is not None else opportunity(),
            buyer if buyer is not None else party("buyer","b1"),suppliers,**args)

    def test_exact_compatible_candidate(self):
        result=self.match([party("supplier","s1")])[0]
        self.assertTrue(result.eligible_for_review)
        self.assertEqual(result.reasons,())
        self.assertEqual(result.supplier.capacity,Decimal("2000"))
        self.assertEqual(result.supplier.source_url,"https://example.org/registry")

    def test_identity_is_scheme_scoped(self):
        a=normalize_party(party("buyer","123"))
        b=normalize_party(party("supplier","123",scheme="OTHER"))
        self.assertNotEqual(a.key,b.key)
        self.assertEqual(a.key,normalize_party(party("supplier","123")).key)

    def test_reject_same_identity_and_wrong_role(self):
        rows=self.match([party("buyer","b1"),party("buyer","b2")])
        by_id={r.supplier.identifier:r for r in rows}
        self.assertIn("SAME_ORGANIZATION",by_id["b1"].reasons)
        self.assertIn("SUPPLIER_ROLE_MISSING",by_id["b2"].reasons)
        self.assertFalse(any(r.eligible_for_review for r in rows))

    def test_financial_and_classification_constraints(self):
        row=self.match([party("supplier","s1",currency="EUR",capacity="5",
            classifications=[dict(scheme="CPV",code="99999999")],regions=["US-NY"])])[0]
        self.assertIn("SUPPLIER_CURRENCY_MISMATCH",row.reasons)
        self.assertIn("SUPPLIER_CLASSIFICATION_MISSING",row.reasons)
        self.assertIn("SUPPLIER_REGION_MISMATCH",row.reasons)
        self.assertFalse(row.eligible_for_review)
        row=self.match([party("supplier","s2",capacity="999.99")])[0]
        self.assertIn("SUPPLIER_CAPACITY_INSUFFICIENT",row.reasons)

    def test_buyer_and_stale_opportunity_fail(self):
        row=self.match([party("supplier","s1")],buyer=party("supplier","b1",capacity="50"),
            op=opportunity(retrieved_at="2026-11-20T12:00:00Z"))[0]
        self.assertIn("BUYER_ROLE_MISSING",row.reasons)
        self.assertIn("BUYER_CAPACITY_INSUFFICIENT",row.reasons)
        self.assertIn("OPPORTUNITY_STALE_OBSERVATION",row.reasons)
        self.assertFalse(row.eligible_for_review)

    def test_party_freshness(self):
        row=self.match([party("supplier","s1",observed_at="2026-11-20T12:00:00Z")])[0]
        self.assertIn("SUPPLIER_STALE_OBSERVATION",row.reasons)
        row=self.match([party("supplier","s2",observed_at="2026-11-25T12:00:00Z")])[0]
        self.assertIn("SUPPLIER_FUTURE_OBSERVATION",row.reasons)

    def test_order_independent_and_duplicate_rejected(self):
        a,b=party("supplier","s1"),party("supplier","s2")
        self.assertEqual(self.match([a,b]),self.match([b,a]))
        with self.assertRaises(ValueError):
            self.match([a,a])

    def test_malformed_inputs(self):
        for raw in (party("supplier","s1",capacity="NaN"),
                    party("supplier","s1",classifications=[]),
                    party("supplier","s1",regions=["US-CA","US-CA"]),
                    party("supplier","s1",source_url="http://example.org"),
                    party("supplier","s1",roles=["admin"]),
                    party("supplier","s1",identifier=" s1")):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_party(raw)

    def test_halt_precedes_input_validation(self):
        for halted in (True,None,0):
            with patch("nexus_exchange.atlas.normalize_party") as parser:
                with self.assertRaises(PermissionError):
                    self.match([{}],halted=halted)
                parser.assert_not_called()

    def test_bounded_batch_and_requirements(self):
        with self.assertRaises(ValueError):
            self.match([party("supplier",str(i)) for i in range(101)])
        with self.assertRaises(ValueError):
            self.match([party("supplier","s1")],classifications=[])
