"""Historical receipt inspection on real synthetic comparison projections."""
import copy
from datetime import timedelta
import unittest

from nexus_exchange.operator_drafts import _digest, _json
from nexus_exchange.quote_comparison import compare_quotes
from nexus_exchange.quote_history import (historical_receipt, inspect_receipt,
    index_receipts, MAX_RECEIPT_BYTES, MAX_INDEX_RECEIPTS)
import test_quote_comparison as fixtures
from test_operator_drafts import NOW


def encode(receipt):
    return (_json(receipt) + "\n").encode("ascii")


def rehash(value, key):
    value.pop(key, None)
    value[key] = _digest(_json(value))


class QuoteHistoryInspectionTests(unittest.TestCase):
    def setUp(self):
        self.entries = fixtures.QuoteComparisonTests().pair()
        self.original = compare_quotes(self.entries, now=NOW, halted=False)
        self.scope = self.original["scope_sha256"]

    def receipt(self, seconds=1):
        current = compare_quotes(self.entries, now=NOW+timedelta(seconds=seconds), halted=False)
        return historical_receipt(self.original, current)

    def test_minimal_historical_metadata(self):
        receipt = self.receipt()
        view = inspect_receipt(encode(receipt))
        self.assertEqual(view["receipt_sha256"], receipt["receipt_sha256"])
        self.assertEqual(view["lowest_declared_total_cents"], 975)
        self.assertEqual(view["quote_count"], 2)
        self.assertEqual(view["current_status"], "NOT_REVALIDATED")
        self.assertIs(view["external_authority"], False)
        self.assertNotIn("supplier", view)
        self.assertNotIn("rows", view)

    def test_index_scope_replay_and_halt(self):
        first, second = encode(self.receipt()), encode(self.receipt(2))
        result = index_receipts([first, second, first], scope_sha256=self.scope, halted=False)
        self.assertEqual(len(result), 2)
        self.assertGreater(result[0]["rechecked_at"], result[1]["rechecked_at"])
        self.assertEqual(index_receipts([first], scope_sha256="f"*64, halted=False), [])
        for halted in (None, True, 0):
            with self.assertRaises(PermissionError):
                index_receipts([first], scope_sha256=self.scope, halted=halted)
        with self.assertRaises(ValueError):
            index_receipts([first]*(MAX_INDEX_RECEIPTS+1), scope_sha256=self.scope, halted=False)
        with self.assertRaises(ValueError):
            index_receipts([first, b"{}"], scope_sha256=self.scope, halted=False)

    def test_reject_noncanonical_or_tampered_bytes(self):
        good = encode(self.receipt())
        for raw in (good[:-1], b" "+good, b"\xff", b"["*2000, b"x"*(MAX_RECEIPT_BYTES+1),
                    good.replace(b'"historical_only":true', b'"historical_only":true,"historical_only":true')):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                inspect_receipt(raw)
        receipt = self.receipt()
        receipt["rechecked_comparison_sha256"] = "a"*64
        rehash(receipt, "receipt_sha256")
        with self.assertRaises(ValueError):
            inspect_receipt(encode(receipt))

    def test_rehashed_inconsistent_comparison_rejected(self):
        for change in ("total", "ranking", "extra", "authority"):
            result = copy.deepcopy(self.original)
            if change == "total":
                row = result["rows"][0]
                row["total_cents"] += 1
                rehash(row, "declaration_sha256")
            elif change == "ranking":
                result["lowest_declared_total_cents"] = 1
            elif change == "extra":
                result["rows"][0]["raw_reply"] = "untrusted"
                rehash(result["rows"][0], "declaration_sha256")
            else:
                result["external_authority"] = True
            rehash(result, "comparison_sha256")
            # Build a deliberately forged but self-hashed envelope independently.
            receipt = self.receipt()
            receipt["comparison"] = result
            current = dict(result, compared_at=receipt["rechecked_at"])
            rehash(current, "comparison_sha256")
            receipt["rechecked_comparison_sha256"] = current["comparison_sha256"]
            rehash(receipt, "receipt_sha256")
            with self.subTest(change=change), self.assertRaises(ValueError):
                inspect_receipt(encode(receipt))

    def test_rehashed_duplicate_quotation_identities_rejected(self):
        for key in ("draft_id", "recipient_id", "thread_id", "reply_sha256"):
            receipt = self.receipt()
            result = receipt["comparison"]
            first, second = result["rows"]
            second[key] = first[key]
            rehash(second, "declaration_sha256")
            rehash(result, "comparison_sha256")
            current = dict(result, compared_at=receipt["rechecked_at"])
            rehash(current, "comparison_sha256")
            receipt["rechecked_comparison_sha256"] = current["comparison_sha256"]
            rehash(receipt, "receipt_sha256")
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "duplicate historical quotation identity"):
                inspect_receipt(encode(receipt))

    def test_unequal_timing_and_ties_remain_historical(self):
        fixture = fixtures.QuoteComparisonTests()
        for entries, expected in ((fixture.pair(delivery_days=5), None),
                                  ([fixture.entry(), fixture.entry("SUPPLIER-2", "c")], 1175)):
            original = compare_quotes(entries, now=NOW, halted=False)
            current = compare_quotes(entries, now=NOW+timedelta(seconds=1), halted=False)
            view = inspect_receipt(encode(historical_receipt(original, current)))
            self.assertEqual(view["lowest_declared_total_cents"], expected)
            self.assertEqual(view["current_status"], "NOT_REVALIDATED")
            self.assertIs(view["execution_eligible"], False)
