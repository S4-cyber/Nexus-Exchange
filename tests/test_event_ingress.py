"""Journal ingress must reject malformed events before serialization or writes."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from nexus_exchange.dashboard_events import project
from nexus_exchange.event_store import EventStore


def event(state="queued", **changes):
    result = dict(task_id="fixture", target="offline", state=state,
                  timestamp="2026-01-01T00:00:00Z")
    result.update(changes)
    return result


class EventIngressTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore(":memory:")
        self.addCleanup(self.store.close)

    def test_invalid_input_rejected_before_serialization(self):
        class Key(str):
            pass

        altered = event()
        altered[Key("target")] = altered.pop("target")
        cases = ([], event(target="x" * 100000), event(target=["nested"]),
                 event(extra="unexpected"), altered, event(timestamp="bad"),
                 event(state="unknown"), event(task_id="\ud800"))
        for raw in cases:
            with self.subTest(raw_type=type(raw).__name__):
                with patch("nexus_exchange.event_store._encode", side_effect=AssertionError("serialized invalid input")):
                    with self.assertRaises(ValueError):
                        self.store.append(raw)
                self.assertEqual(self.store.read(), ())
                self.assertFalse(self.store.db.in_transaction)

    def test_escaped_surrogate_history_is_maintenance_hold(self):
        raw = json.dumps(event(target="\udfff"), ensure_ascii=True)
        self.store.db.execute("INSERT INTO events(payload) VALUES (?)", (raw,))
        for operation in (self.store.read,
                          lambda: self.store.append(event("running")),
                          lambda: self.store.recover_interrupted(now=datetime(2026, 1, 2, tzinfo=timezone.utc))):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()
                self.assertEqual(self.store.db.execute("SELECT payload FROM events").fetchone()[0], raw)
                self.assertFalse(self.store.db.in_transaction)

    def test_projection_rejects_non_scalar_unicode(self):
        with self.assertRaises(ValueError):
            project((event(task_id="\ud800"),))

    def test_valid_unicode_and_legacy_whitespace_remain_compatible(self):
        first = event(task_id="  🌱  ", target=" 🌳 " )
        second = event("running", task_id="🌱", target="🌳")
        self.store.append(first)
        self.store.append(second)
        self.assertEqual(self.store.read(), (first, second))
        self.assertEqual(self.store.recover_interrupted(now=datetime(2026, 1, 2, tzinfo=timezone.utc)), 1)
        self.assertEqual(self.store.read()[-1]["task_id"], "🌱")

    def test_valid_fields_still_require_legal_transitions(self):
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            self.store.append(event("running"))
        self.assertEqual(self.store.read(), ())
        self.store.append(event())
        with self.assertRaisesRegex(ValueError, "target changed"):
            self.store.append(event("running", target="another"))
        self.assertEqual(self.store.read(), (event(),))
