"""The native activity view must use the bounded journal projection."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from nexus_exchange.activity_feed import ActivityFeed
from nexus_exchange.event_store import EventStore


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def event(state="queued", **changes):
    result = dict(task_id="fixture", target="offline", state=state,
                  timestamp="2026-01-01T00:00:00Z")
    result.update(changes)
    return result


class ActivityJournalTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore(":memory:")
        self.addCleanup(self.store.close)
        self.feed = ActivityFeed(self.store.db)
        self.feed.put("scout", [("finding-1", "Finding", "Scout fixture", "Independent evidence")], NOW)

    def raw(self, payload):
        self.store.db.execute("INSERT INTO events(payload) VALUES (?)", (payload,))

    def assert_hold(self):
        before = self.store.db.total_changes
        rows = self.feed.snapshot()
        self.assertEqual(self.store.db.total_changes, before)
        self.assertFalse(self.store.db.in_transaction)
        self.assertIn(("finding-1", "Finding", "Scout fixture"), [r[:3] for r in rows])
        journal = [r for r in rows if r[0].startswith("journal-")]
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0][:3], ("journal-review-required", "Needs attention", "Task journal unavailable"))
        self.assertNotIn("private-fixture", repr(rows))

    def test_corrupt_payloads_are_not_rendered_or_silently_skipped(self):
        valid = json.dumps(event())
        cases = (valid.encode(), valid[:-1] + ', "state": "queued"}',
                 json.dumps(event(target="private-fixture" + "x" * 8192)),
                 json.dumps(event(target="private-fixture\ud800")),
                 json.dumps(event("succeeded", target="private-fixture")),
                 '{not JSON private-fixture')
        for payload in cases:
            with self.subTest(payload_type=type(payload).__name__, length=len(payload)):
                self.store.db.execute("DELETE FROM events")
                self.raw(payload)
                self.assert_hold()

    def test_corrupt_older_history_is_checked_before_display_limit(self):
        self.raw(json.dumps(event("running", task_id="private-fixture")))
        self.raw(json.dumps(event(task_id="newer")))
        with patch("nexus_exchange.activity_feed.LIMIT", 1):
            self.assert_hold()

    def test_storage_type_and_aggregate_capacity_are_shared_with_journal(self):
        self.raw(json.dumps(event()))
        self.raw(json.dumps(event("running")))
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES", 150):
            self.assert_hold()
        with patch("nexus_exchange.event_store.MAX_RECOVERY_EVENTS", 1):
            self.assert_hold()
        self.store.db.execute("UPDATE events SET payload=CAST(X'FF' AS TEXT) WHERE seq=1")
        self.assert_hold()

    def test_normalized_identity_and_utc_transitions(self):
        self.store.append(event(task_id="  🌱  ", target=" 🌳 ", timestamp="2026-01-01T02:00:00+02:00"))
        self.store.append(event("running", task_id="🌱", target="🌳", timestamp="2026-01-01T00:01:00Z"))
        self.store.append(event("succeeded", task_id="🌱", target="🌳", timestamp="2026-01-01T00:02:00Z"))
        journal, = [r for r in self.feed.snapshot() if r[0].startswith("journal-")]
        self.assertEqual(journal[:3], ("journal-🌱", "Completed", "🌳"))
        self.assertIn("Pending 2026-01-01 00:00:00 UTC", journal[3])
        self.assertIn("Completed 2026-01-01 00:02:00 UTC", journal[3])
        self.assertEqual(journal[4], "2026-01-01T00:02:00+00:00")

    def test_display_limit_applies_after_full_history_validation(self):
        for state in ("queued", "running", "succeeded"):
            self.store.append(event(state))
        with patch("nexus_exchange.activity_feed.LIMIT", 1):
            journal, = [r for r in self.feed.snapshot() if r[0].startswith("journal-")]
        self.assertEqual(journal[:3], ("journal-fixture", "Completed", "offline"))
        self.assertNotIn("Pending", journal[3])

    def test_missing_journal_table_retains_independent_scout_rows(self):
        self.store.db.execute("DROP TABLE events")
        self.assert_hold()
