"""Runtime quotation comparison: real archive, stores and synthetic replies."""
import copy
import unittest
from datetime import timedelta

import test_operator_scenario_integration as prior
from nexus_exchange.evidence import fingerprint
from nexus_exchange.operator_drafts import _stamp
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.runtime_guard import RuntimeGuard
from test_owner_profile import profile


class QuoteRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = prior.OperatorRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard = self.fixture.guard
        self.guard.resume()

    def action(self, action, **inputs):
        return self.guard.operator_action(action, self.fixture.key, **inputs)

    def entry(self, number, cents):
        f = self.fixture
        supplier = f.supplier(identifier="SYNTHETIC-"+str(number))
        draft = f.call(supplier=supplier)["draft"]
        path = f.directory/("contact-"+str(number)+".txt")
        path.write_bytes(("synthetic contact "+str(number)).encode())
        recipient = dict(scheme=supplier["scheme"], identifier=supplier["identifier"],
            organization_name=supplier["name"], email="quotes@example.org",
            source_url="https://example.org/contact", observed_at=f.now.isoformat())
        args = dict(draft_id=draft["draft_id"], supplier=supplier,
                    recipient=recipient, evidence_path=path)
        preview = self.action("recipient_preview", **args)
        self.action("recipient_save", **args, expected_recipient_id=preview["recipient_id"],
                    confirmed=True)
        scope = dict(draft_id=draft["draft_id"], recipient_id=preview["recipient_id"])
        opened = self.action("thread_open", **scope, supplier=supplier, confirmed=True)
        path.write_bytes(("synthetic reply "+str(number)).encode())
        reference = fingerprint(path, halted=False)
        thread = self.action("thread_append", **scope, supplier=supplier,
            kind="SIMULATED_REPLY", evidence_path=path, expected_head=opened["head_sha256"],
            expected_evidence=reference, confirmed=True)
        declaration = dict(expected_head=thread["head_sha256"], evidence_reference=reference,
            currency="USD", line_totals_cents=[cents], tax_cents=0, shipping_cents=0,
            fees_cents=0, delivery_days=3, payment_days=30,
            valid_until=_stamp(f.now+timedelta(days=1)))
        return dict(**scope, supplier=supplier, declaration=declaration)

    def test_saved_records_restart_and_no_authority(self):
        entries = [self.entry(1, 1000), self.entry(2, 800)]
        with self.assertRaises(PermissionError):
            self.action("quote_compare", entries=entries, confirmed=False)
        result = self.action("quote_compare", entries=entries, confirmed=True)
        self.assertEqual(result["lowest_declared_total_cents"], 800)
        self.assertEqual(result["plan_id"], self.fixture.key)
        self.assertFalse(result["supplier_selected"])
        self.assertFalse(result["payment_authorized"])
        self.assertFalse(result["terms_verified"])
        self.assertEqual(result, self.action("quote_compare", entries=entries[::-1], confirmed=True))
        self.guard.close()
        self.guard = RuntimeGuard(self.fixture.directory, clock=lambda:self.fixture.now)
        self.addCleanup(self.guard.close)
        with self.assertRaises(PermissionError):
            self.action("quote_compare", entries=entries, confirmed=True)
        self.guard.resume()
        self.assertEqual(result, self.action("quote_compare", entries=entries, confirmed=True))

    def test_reject_forged_snapshot_stale_reply_supplier_and_profile(self):
        entries = [self.entry(1, 1000), self.entry(2, 800)]
        for field, value in (("recipient_id", "a"*64), ("draft_id", "b"*64),
                             ("draft", {})):
            changed = copy.deepcopy(entries)
            changed[0][field] = value
            with self.assertRaises(ValueError):
                self.action("quote_compare", entries=changed, confirmed=True)
        changed = copy.deepcopy(entries)
        changed[0]["supplier"]["capacity"] = "2000.00"
        with self.assertRaises(ValueError):
            self.action("quote_compare", entries=changed, confirmed=True)
        e = entries[0]
        path = self.fixture.directory/"new-reply.txt"
        path.write_bytes(b"new synthetic reply")
        self.action("thread_append", draft_id=e["draft_id"], recipient_id=e["recipient_id"],
            supplier=e["supplier"], kind="SIMULATED_REPLY", evidence_path=path,
            expected_head=e["declaration"]["expected_head"],
            expected_evidence=fingerprint(path, halted=False), confirmed=True)
        with self.assertRaises(ValueError):
            self.action("quote_compare", entries=entries, confirmed=True)
        # Refresh the declaration to isolate a separate profile supersession.
        current = self.action("thread_history", draft_id=e["draft_id"], recipient_id=e["recipient_id"])
        e["declaration"]["expected_head"] = current["head_sha256"]
        e["declaration"]["evidence_reference"] = current["events"][-1]["evidence_reference"]
        self.assertEqual(self.action("quote_compare", entries=entries, confirmed=True)
                         ["lowest_declared_total_cents"], 800)
        with ProfileStore(self.fixture.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30), halted=False)
        with self.assertRaises(ValueError):
            self.action("quote_compare", entries=entries, confirmed=True)
