import unittest
from decimal import Decimal, localcontext
from test_atlas import NOW, CODE, REGION, party, opportunity
from nexus_exchange.economics import assess_deal

def terms(**overrides):
    raw=dict(currency="USD",fee_if_collected="200",upfront_cost="20",
        completion_cost="40",probability_completion="0.5",probability_collection_given_completion="0.8",
        exposure_limit="100",assumptions="Synthetic fee and cost assumptions; not an agreed contract.")
    raw.update(overrides)
    return raw

class EconomicsTests(unittest.TestCase):
    def evaluate(self, raw=None, buyer=None, supplier=None, op=None, halted=False):
        return assess_deal(op if op is not None else opportunity(),
            buyer if buyer is not None else party("buyer","b1"),
            supplier if supplier is not None else party("supplier","s1"),
            classifications=[dict(scheme=CODE[0],code=CODE[1])],region=REGION,
            terms=terms() if raw is None else raw,now=NOW,halted=halted)

    def test_conditional_collection_and_costs(self):
        result=self.evaluate()
        self.assertEqual(result.expected_fee,Decimal("80"))
        self.assertEqual(result.expected_cost,Decimal("40"))
        self.assertEqual(result.expected_net,Decimal("40"))
        self.assertEqual(result.net_if_paid,Decimal("140"))
        self.assertEqual(result.maximum_modeled_loss,Decimal("60"))
        self.assertTrue(result.eligible_for_review)
        self.assertFalse(result.external_authority)

    def test_tender_budget_not_revenue(self):
        a=self.evaluate()
        b=self.evaluate(op=opportunity(amount="1500"))
        self.assertEqual(a.expected_fee,b.expected_fee)

    def test_declared_loss_limit(self):
        result=self.evaluate(terms(exposure_limit="59.99"))
        self.assertIn("EXPOSURE_LIMIT_EXCEEDED",result.reasons)
        self.assertFalse(result.eligible_for_review)

    def test_unprofitable_scenario(self):
        result=self.evaluate(terms(probability_collection_given_completion="0"))
        self.assertEqual(result.expected_net,Decimal("-40"))
        self.assertIn("NONPOSITIVE_EXPECTED_NET",result.reasons)

    def test_completion_cost_not_assumed_when_not_completed(self):
        result=self.evaluate(terms(probability_completion="0"))
        self.assertEqual(result.expected_cost,Decimal("20"))
        self.assertEqual(result.expected_net,Decimal("-20"))
        self.assertEqual(result.maximum_modeled_loss,Decimal("60"))

    def test_failed_matching_cannot_be_rescued_by_profit(self):
        result=self.evaluate(supplier=party("supplier","s1",capacity="1"))
        self.assertGreater(result.expected_net,0)
        self.assertIn("SUPPLIER_CAPACITY_INSUFFICIENT",result.reasons)
        self.assertFalse(result.eligible_for_review)

    def test_zero_cost_model_and_perfect_collection(self):
        result=self.evaluate(terms(upfront_cost="0",completion_cost="0",exposure_limit="0",
            probability_completion="1",probability_collection_given_completion="1"))
        self.assertEqual(result.expected_net,Decimal("200"))
        self.assertEqual(result.maximum_modeled_loss,0)

    def test_exact_decimal_under_low_ambient_precision(self):
        with localcontext() as ctx:
            ctx.prec=3
            result=self.evaluate(terms(fee_if_collected="1234.5678",upfront_cost="0",
                completion_cost="0",probability_completion="0.123456",
                probability_collection_given_completion="0.654321"))
        self.assertEqual(result.expected_fee,Decimal("1234.5678")*Decimal("0.123456")*Decimal("0.654321"))

    def test_reject_invalid_assumptions(self):
        for raw in (terms(currency="EUR"),terms(fee_if_collected="NaN"),
            terms(upfront_cost="-1"),terms(probability_completion="1.01"),
            terms(probability_completion=0.5),terms(exposure_limit="Infinity"),
            terms(assumptions=""),terms(completion_cost="1e3")):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                self.evaluate(raw)
        raw=terms()
        del raw["fee_if_collected"]
        with self.assertRaises(ValueError):
            self.evaluate(raw)

    def test_halt_overrides_all_inputs(self):
        for state in (True,None,0):
            with self.assertRaises(PermissionError):
                self.evaluate(raw={},halted=state)
