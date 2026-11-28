"""Synthetic quote declarations use real RFQ, recipient and thread validators."""
import copy
from datetime import timedelta
import unittest

from nexus_exchange.correspondence_thread import open_thread, append_event
from nexus_exchange.operator_drafts import _stamp
from nexus_exchange.operator_recipients import prepare_recipient
from nexus_exchange.quote_comparison import compare_quotes, MAX_CENTS
from test_operator_drafts import NOW
from test_operator_recipients import draft, contact, REFERENCE


class QuoteComparisonTests(unittest.TestCase):
    def entry(self, supplier="SUPPLIER-1", ref="b", cents=1000, **changes):
        rfq = draft(supplier=dict(scheme="REGISTRY", identifier=supplier))
        recipient = prepare_recipient(rfq, contact(identifier=supplier),
            organization_name="Synthetic supplier", evidence_reference=REFERENCE,
            now=NOW, halted=False)
        thread = open_thread(rfq, recipient, now=NOW, confirmed=True, halted=False)
        thread = append_event(rfq, recipient, thread, kind="SIMULATED_REPLY",
            evidence_reference="sha256:"+ref*64+";bytes:24", now=NOW,
            expected_head=thread["head_sha256"], confirmed=True, halted=False)
        declaration = dict(expected_head=thread["head_sha256"],
            evidence_reference=thread["events"][-1]["evidence_reference"], currency="USD",
            line_totals_cents=[cents], tax_cents=100, shipping_cents=50, fees_cents=25,
            delivery_days=3, payment_days=30, valid_until=_stamp(NOW+timedelta(days=1)))
        declaration.update(changes)
        return dict(draft=rfq, recipient=recipient, thread=thread, declaration=declaration)

    def pair(self, **changes):
        return [self.entry(), self.entry("SUPPLIER-2", "c", 800, **changes)]

    def test_exact_costs_order_and_no_authority(self):
        entries = self.pair()
        original = copy.deepcopy(entries)
        result = compare_quotes(entries, now=NOW, halted=False)
        self.assertEqual([r["total_cents"] for r in result["rows"]], [975, 1175])
        self.assertEqual(result["lowest_declared_total_cents"], 975)
        self.assertEqual(len(result["lowest_declared_cost_ids"]), 1)
        self.assertEqual(result, compare_quotes(entries[::-1], now=NOW, halted=False))
        self.assertEqual(entries, original)
        for k in ("external_authority", "reply_authenticated", "terms_verified",
                  "execution_eligible", "supplier_selected", "payment_authorized"):
            self.assertIs(result[k], False)
        self.assertNotIn("quotes@example.org", str(result))

    def test_timing_difference_withholds_cost_selection_and_ties_preserved(self):
        result = compare_quotes(self.pair(delivery_days=5), now=NOW, halted=False)
        self.assertEqual(result["status"], "DIFFERENT_TIMING_REVIEW")
        self.assertIsNone(result["lowest_declared_total_cents"])
        self.assertEqual(result["lowest_declared_cost_ids"], [])
        entries = [self.entry(), self.entry("SUPPLIER-2", "c")]
        result = compare_quotes(entries, now=NOW, halted=False)
        self.assertEqual(len(result["lowest_declared_cost_ids"]), 2)

    def test_reject_unbounded_unknown_expired_or_mismatched_declarations(self):
        for changes in (dict(currency="EUR"), dict(line_totals_cents=[]),
                        dict(line_totals_cents=[True]), dict(line_totals_cents=[-1]),
                        dict(line_totals_cents=[MAX_CENTS]), dict(tax_cents=None),
                        dict(payment_days=True), dict(valid_until=_stamp(NOW)),
                        dict(valid_until=_stamp(NOW+timedelta(days=366))),
                        dict(expected_head="e"*64), dict(evidence_reference=REFERENCE),
                        dict(external_authority=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                compare_quotes(self.pair(**changes), now=NOW, halted=False)

    def test_scope_duplicates_tamper_and_halt(self):
        entries = self.pair()
        for halted in (None, True, 0):
            with self.assertRaises(PermissionError):
                compare_quotes(entries, now=NOW, halted=halted)
        for pair in ([self.entry(), self.entry()],
                     [self.entry(), self.entry("SUPPLIER-2", "b")]):
            with self.assertRaises(ValueError):
                compare_quotes(pair, now=NOW, halted=False)
        for changed in ("draft", "thread", "recipient"):
            pair = copy.deepcopy(entries)
            pair[1][changed] = pair[0][changed]
            with self.assertRaises(ValueError):
                compare_quotes(pair, now=NOW, halted=False)
        with self.assertRaises(ValueError):
            compare_quotes(entries, now=NOW-timedelta(seconds=1), halted=False)
        for pair in ([], entries[:1], entries*9):
            with self.assertRaises(ValueError):
                compare_quotes(pair, now=NOW, halted=False)


if __name__ == "__main__":
    unittest.main()
