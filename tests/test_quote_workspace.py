import unittest
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_explicit_history_file_preserves_exact_review_without_overwrite(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        with TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "review.json"
            with self.assertRaises(ValueError):
                self.review.history_pin()
            result = self.review.compare(confirmed=True)
            pin = self.review.history_pin()
            for confirmed in (None, False, 1):
                with self.assertRaises(PermissionError):
                    self.review.export_history(target, expected_comparison=pin, confirmed=confirmed)
            self.assertFalse(target.exists())
            digest = self.review.export_history(target, expected_comparison=pin, confirmed=True)
            content = target.read_bytes()
            self.assertEqual(digest, hashlib.sha256(content).hexdigest())
            receipt = json.loads(content)
            self.assertEqual(receipt["comparison"], result)
            self.assertIs(receipt["historical_only"], True)
            self.assertIs(receipt["current_decision"], False)
            self.assertIs(receipt["external_authority"], False)
            with self.assertRaises(FileExistsError):
                self.review.export_history(target, expected_comparison=pin, confirmed=True)
            self.assertEqual(target.read_bytes(), content)
            # Windows TEMP can use an 8.3 alias while resolve() expands it.
            # Check the exact directory contents and file identity, not spelling.
            entries = list(Path(directory).iterdir())
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].name, target.name)
            self.assertTrue(entries[0].samefile(target))

    def test_history_rejects_changed_review_and_halt(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        result = self.review.compare(confirmed=True)
        pin = self.review.history_pin()
        with TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "review.json"
            self.workspace.action = Mock(return_value=dict(result, lowest_declared_total_cents=801))
            with self.assertRaises(ValueError):
                self.review.export_history(target, expected_comparison=pin, confirmed=True)
            self.assertFalse(target.exists())
            self.workspace.action = self.guard.operator_action
            self.review.compare(confirmed=True)
            pin = self.review.history_pin()
            self.guard.set()
            with self.assertRaises(PermissionError):
                self.review.export_history(target, expected_comparison=pin, confirmed=True)
            self.assertFalse(target.exists())
            self.review.clear()
            self.guard.resume()
            with self.assertRaises(ValueError):
                self.review.history_pin()

    def test_comparison_rejects_numeric_type_substitution(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        result = self.review.compare(confirmed=True)
        self.workspace.action = Mock(return_value=dict(result, lowest_declared_total_cents=800.0))
        with self.assertRaises(ValueError):
            self.review.compare(confirmed=True)

    def test_inspect_selected_history_files_without_restaging_or_authority(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        result = self.review.compare(confirmed=True)
        before = self.review.summary()
        with TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "history.json"
            self.review.export_history(target, expected_comparison=self.review.history_pin(),
                                       confirmed=True)
            original = target.read_bytes()
            rows = self.review.inspect_history_files((target, target))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["scope_sha256"], result["scope_sha256"])
            self.assertEqual(rows[0]["lowest_declared_total_cents"], 800)
            self.assertEqual(rows[0]["current_status"], "NOT_REVALIDATED")
            self.assertIs(rows[0]["execution_eligible"], False)
            self.assertNotIn("rows", rows[0])
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(self.review.summary(), before)
            with self.assertRaises(ValueError):
                self.review.history_pin()
            other_plan = "f"*64 if self.workspace.plan_id != "f"*64 else "e"*64
            foreign = QuoteReview(OperatorWorkspace(other_plan, action=Mock(),
                                  blocked_check=self.guard.is_set))
            with self.assertRaisesRegex(ValueError, "outside selected saved plan"):
                foreign.inspect_history_files([target])
            foreign.workspace.action.assert_not_called()

    def test_history_file_batch_rejects_invalid_inputs_and_halt(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        self.review.compare(confirmed=True)
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            good = root / "history.json"
            self.review.export_history(good, expected_comparison=self.review.history_pin(),
                                       confirmed=True)
            bad = root / "bad.json"
            bad.write_bytes(b"{}")
            large = root / "large.json"
            large.write_bytes(b"x" * (64*1024+1))
            for paths in ([], [good]*65, [good, bad], [large], ["relative.json"]):
                with self.subTest(count=len(paths)), self.assertRaises(ValueError):
                    self.review.inspect_history_files(paths)
            self.guard.set()
            with self.assertRaises(PermissionError):
                self.review.inspect_history_files([good])


    def test_retained_history_controls_use_exact_plan_and_confirmation(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        self.review.compare(confirmed=True)
        original_action = self.workspace.action

        def route(action, plan, **inputs):
            if action.startswith("quote_history_"):
                return self.guard.quote_history_action(action.removeprefix("quote_history_"), plan, **inputs)
            return original_action(action, plan, **inputs)

        self.workspace.action = route
        with TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "receipt.json"
            self.review.export_history(target, expected_comparison=self.review.history_pin(), confirmed=True)
            documents, preview = self.review._read_history_files([target])
            self.assertEqual(self.review.retained_history(), [])
            for confirmation in (None, False, 1):
                with self.assertRaises(PermissionError):
                    self.review.retain_history(documents, confirmed=confirmation)
            self.assertEqual(self.review.retained_history(), [])
            target.write_bytes(b"{}")  # Retention uses the exact inspected bytes, not a second file read.
            rows = self.review.retain_history(documents, confirmed=True)
            self.assertEqual(rows, preview)
            self.assertEqual(self.review.retained_history(), preview)
            self.assertEqual(self.review.retain_history(documents, confirmed=True), preview)
            key = rows[0]["receipt_sha256"]
            with self.assertRaises(PermissionError):
                self.review.forget_history(key, confirmed=1)
            with self.assertRaises(ValueError):
                self.review.history_pin()
            self.assertEqual(self.review.forget_history(key, confirmed=True), [])
            self.assertEqual(self.review.retained_history(), [])
            self.assertEqual(target.read_bytes(), b"{}")
            self.guard.set()
            with self.assertRaises(PermissionError):
                self.review.retained_history()

    def test_retained_projection_rejects_forged_authority_or_lineage(self):
        a, b = self.fixture.entry(1, 1000), self.fixture.entry(2, 800)
        self.stage(a)
        self.stage(b)
        self.review.compare(confirmed=True)
        with TemporaryDirectory() as directory:
            target = Path(directory).resolve() / "receipt.json"
            self.review.export_history(target, expected_comparison=self.review.history_pin(), confirmed=True)
            row = self.review.inspect_history_files([target])[0]
            for change in ({"external_authority": True}, {"plan_id": "f"*64},
                           {"snapshot_observations": True}, {"scope_snapshots": 2},
                           {"supersession_status": "CURRENT"}, {"quote_count": True}):
                self.workspace.action = Mock(return_value=[dict(row, **change)])
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.review.retained_history()
