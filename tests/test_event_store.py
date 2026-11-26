import tempfile
import unittest
from pathlib import Path
from nexus_exchange.event_store import EventStore

def event(state):
    return dict(task_id="a",target="fixture",state=state,timestamp="2026-01-01T00:00:00Z")

class StoreTests(unittest.TestCase):
    def test_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"events.db"
            s=EventStore(p)
            s.append(event("queued"))
            s.close()
            s=EventStore(p)
            try:
                s.append(event("running"))
                self.assertEqual(len(s.read()),2)
            finally: s.close()
    def test_rollback(self):
        s=EventStore(":memory:")
        try:
            s.append(event("queued"))
            with self.assertRaises(ValueError): s.append(event("succeeded"))
            self.assertEqual(s.read(),(event("queued"),))
        finally: s.close()

    def test_ignored_append_rejected(self):
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.db.execute("CREATE TRIGGER ignore_event BEFORE INSERT ON events BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaisesRegex(ValueError,"journal mutation not persisted"):
            s.append(event("queued"))
        self.assertEqual(s.read(),())
        self.assertFalse(s.db.in_transaction)

    def test_append_rewrite_history_rolled_back(self):
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.append(event("queued"))
        s.db.execute("""CREATE TRIGGER rewrite_event AFTER INSERT ON events
            BEGIN UPDATE events SET payload=json_set(payload,'$.target','changed') WHERE seq=1; END""")
        with self.assertRaisesRegex(ValueError,"journal mutation not persisted"):
            s.append(event("running"))
        self.assertEqual(s.read(),(event("queued"),))
        self.assertFalse(s.db.in_transaction)

    def test_recovery_partial_insert_rolled_back(self):
        from datetime import datetime, timezone
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.append(event("queued"))
        other=dict(event("queued"),task_id="b")
        s.append(other)
        s.db.execute("""CREATE TRIGGER ignore_recovery BEFORE INSERT ON events
            WHEN json_extract(NEW.payload,'$.task_id')='b'
            BEGIN SELECT RAISE(IGNORE); END""")
        with self.assertRaisesRegex(ValueError,"journal mutation not persisted"):
            s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc))
        self.assertEqual(s.read(),(event("queued"),other))
        self.assertFalse(s.db.in_transaction)
        s.db.execute("DROP TRIGGER ignore_recovery")
        self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),2)
        self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),0)

    def test_append_respects_recovery_capacity(self):
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        with patch("nexus_exchange.event_store.MAX_RECOVERY_EVENTS",2):
            s.append(event("queued"))
            s.append(event("cancelled"))
            with self.assertRaisesRegex(ValueError,"journal recovery capacity"):
                s.append(dict(event("queued"),task_id="b"))
        self.assertEqual(s.read(),(event("queued"),event("cancelled")))
        self.assertFalse(s.db.in_transaction)

    def test_capacity_reserves_interruption_for_active_tasks(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        with patch("nexus_exchange.event_store.MAX_RECOVERY_EVENTS",3):
            s.append(event("queued"))
            s.append(event("running"))
            with self.assertRaisesRegex(ValueError,"journal recovery capacity"):
                s.append(dict(event("queued"),task_id="b"))
            self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),1)
            self.assertEqual(s.read()[-1]["state"],"interrupted")
            self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),0)
