import copy
import unittest
from datetime import timedelta
from unittest.mock import patch

from nexus_exchange.operator_recipients import prepare_recipient
from nexus_exchange.correspondence_thread import open_thread, append_event, validate_thread
from test_operator_recipients import draft, contact, REFERENCE
from test_operator_drafts import NOW


class CorrespondenceThreadTests(unittest.TestCase):
    def setUp(self):
        self.draft = draft()
        self.recipient = prepare_recipient(self.draft, contact(),
            organization_name="Synthetic supplier", evidence_reference=REFERENCE,
            now=NOW, halted=False)
        self.thread = open_thread(self.draft, self.recipient, now=NOW,
                                  confirmed=True, halted=False)

    def append(self, thread=None, **changes):
        thread = self.thread if thread is None else thread
        args = dict(kind="SIMULATED_REPLY", evidence_reference="sha256:"+"b"*64+";bytes:24",
                    now=NOW+timedelta(seconds=1), expected_head=thread["head_sha256"],
                    confirmed=True, halted=False)
        args.update(changes)
        return append_event(self.draft, self.recipient, thread, **args)

    def test_chain_is_deterministic_and_original_unchanged(self):
        first = self.append()
        self.assertEqual(first, self.append())
        self.assertEqual(self.thread["events"], [])
        second = self.append(first, kind="LOCAL_FOLLOWUP_DRAFT",
                            evidence_reference="sha256:"+"c"*64+";bytes:12")
        self.assertEqual(second["events"][1]["parent_sha256"], first["head_sha256"])
        self.assertEqual(second, validate_thread(self.draft, self.recipient, second, halted=False))
        for flag in ("external_authority", "send_enabled", "delivery_verified",
                     "reply_authenticated", "commitment_enabled"):
            self.assertIs(second[flag], False)

    def test_stale_head_and_duplicate_reference(self):
        first = self.append()
        with self.assertRaises(ValueError):
            self.append(first, expected_head=self.thread["head_sha256"])
        with self.assertRaises(ValueError):
            self.append(first)

    def test_forbidden_event_kinds_and_invalid_evidence(self):
        for kind in ("SENT", "DELIVERED", "SIGNED", "PAID", "AUTHENTIC_REPLY", None, []):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.append(kind=kind)
        with self.assertRaises(ValueError):
            self.append(evidence_reference="file:///secret")

    def test_confirm_and_halt_fail_closed(self):
        for state in (True, None, 0):
            with self.assertRaises(PermissionError):
                self.append(halted=state)
            with self.assertRaises(PermissionError):
                validate_thread(self.draft, self.recipient, self.thread, halted=state)
        for confirmation in (False, None, 1):
            with self.assertRaises(PermissionError):
                self.append(confirmed=confirmation)
            with self.assertRaises(PermissionError):
                open_thread(self.draft, self.recipient, now=NOW, confirmed=confirmation, halted=False)

    def test_scope_and_forgery_rejected(self):
        first = self.append()
        for change in (dict(send_enabled=True), dict(delivery_verified=0),
                       dict(recipient_id="e"*64), dict(head_sha256="e"*64)):
            with self.assertRaises(ValueError):
                validate_thread(self.draft, self.recipient, dict(first, **change), halted=False)
        with self.assertRaises(ValueError):
            validate_thread(draft(region="US-NY"), self.recipient, first, halted=False)
        altered = copy.deepcopy(first)
        altered["events"][0]["sequence"] = True
        with self.assertRaises(ValueError):
            validate_thread(self.draft, self.recipient, altered, halted=False)
        altered = copy.deepcopy(first)
        altered["events"][0]["evidence_reference"] = "sha256:"+"f"*64+";bytes:24"
        with self.assertRaises(ValueError):
            validate_thread(self.draft, self.recipient, altered, halted=False)

    def test_time_and_capacity(self):
        with self.assertRaises(ValueError):
            self.append(now=NOW-timedelta(seconds=1))
        with self.assertRaises(ValueError):
            open_thread(self.draft, self.recipient, now=NOW+timedelta(days=2),
                        confirmed=True, halted=False)
        first = self.append()
        with patch("nexus_exchange.correspondence_thread.MAX_EVENTS", 1):
            with self.assertRaises(ValueError):
                self.append(first, evidence_reference="sha256:"+"c"*64+";bytes:12")

    def test_no_raw_content_or_external_claims(self):
        result = self.append(kind="LOCAL_EVIDENCE_DECLARATION")
        self.assertNotIn("quotes@example.org", str(result))
        self.assertNotIn("source_url", str(result))
        bad = copy.deepcopy(result)
        bad["events"][0]["body"] = "untrusted raw message"
        with self.assertRaises(ValueError):
            validate_thread(self.draft, self.recipient, bad, halted=False)
