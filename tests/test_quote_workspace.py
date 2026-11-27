import unittest
from unittest.mock import Mock
from nexus_exchange.operator_workspace import OperatorWorkspace
from nexus_exchange.quote_workspace import QuoteReview, parse_terms
import test_quote_runtime as prior


def terms(entry):
    raw = entry["declaration"]
    return dict(lines=",".join(map(str, raw["line_totals_cents"])),
                tax=str(raw["tax_cents"]), shipping=str(raw["shipping_cents"]),
                fees=str(raw["fees_cents"]), delivery=str(raw["delivery_days"]),
                payment=str(raw["payment_days"]), valid=raw["valid_until"])


def fields(entry):
    raw = entry["supplier"]
    return {k: raw[k] for k in ("scheme", "identifier", "name", "capacity", "source_url", "observed_at")} | {
        "classifications": ",".join(c["scheme"] + ":" + c["code"] for c in raw["classifications"]),
        "regions": ",".join(raw["regions"])}


class QuoteWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = prior.QuoteRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard = self.fixture.guard
        self.workspace = OperatorWorkspace(self.fixture.fixture.key,
            action=self.guard.operator_action, blocked_check=self.guard.is_set)
        self.review = QuoteReview(self.workspace)

    def stage(self, entry):
        self.review.stage(entry["draft_id"], entry["recipient_id"], fields(entry), terms(entry))

    def test_local_staging_and_runtime_comparison(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        with self.assertRaises(ValueError):
            self.stage(a)
        self.stage(b)
        self.assertIn(a["draft_id"], self.review.summary())
        self.assertIn(a["declaration"]["evidence_reference"], self.review.summary())
        for confirmed in (None, False, 1):
            with self.assertRaises(PermissionError):
                self.review.compare(confirmed=confirmed)
        result = self.review.compare(confirmed=True)
        self.assertEqual(result["lowest_declared_total_cents"], 800)
        self.assertFalse(result["supplier_selected"])
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.review.compare(confirmed=True)
        self.review.clear()
        self.guard.resume()
        with self.assertRaises(ValueError):
            self.review.compare(confirmed=True)

    def test_bad_terms_and_result_cannot_be_presented(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        for change in ({"lines": "1.5"}, {"tax": "-1"}, {"payment": "3651"},
                       {"valid": "2026-11-27"}, {"lines": "1,2"}):
            with self.assertRaises(ValueError):
                parse_terms(dict(terms(a), **change), 1)
        self.stage(a)
        self.stage(b)
        result = self.review.compare(confirmed=True)
        self.workspace.action = Mock(return_value=dict(result, payment_authorized=0))
        with self.assertRaises(ValueError):
            self.review.compare(confirmed=True)
        self.workspace.action.return_value = dict(result, lowest_declared_total_cents=1)
        with self.assertRaises(ValueError):
            self.review.compare(confirmed=True)

    def test_recipient_options_are_exact_scope_and_read_only(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        expected = dict(draft_id=a["draft_id"], recipient_ids=(a["recipient_id"],),
                        truncated=False)
        self.assertEqual(self.review.recipient_options(a["draft_id"], fields(a)), expected)
        self.assertEqual(self.review.recipient_options(b["draft_id"], fields(b))["recipient_ids"],
                         (b["recipient_id"],))
        self.assertEqual(self.review.summary(), "")
        with self.assertRaises(ValueError):
            self.review.recipient_options(a["draft_id"], fields(b))
        with self.assertRaises(ValueError):
            self.review.stage(a["draft_id"], b["recipient_id"], fields(a), terms(a))
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.review.recipient_options(a["draft_id"], fields(a))

    def test_changed_declaration_cannot_be_staged_or_listed(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        before = self.review.summary()
        changed = dict(fields(b), capacity="2000.00")
        with self.assertRaises(ValueError):
            self.review.recipient_options(b["draft_id"], changed)
        with self.assertRaises(ValueError):
            self.review.stage(b["draft_id"], b["recipient_id"], changed, terms(b))
        self.assertEqual(self.review.summary(), before)
        self.stage(b)
        self.assertEqual(self.review.compare(confirmed=True)["lowest_declared_total_cents"], 800)
