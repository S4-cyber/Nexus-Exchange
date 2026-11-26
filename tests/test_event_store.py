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

    def test_corrupt_payload_rejected_on_all_paths(self):
        import json
        from datetime import datetime, timezone
        valid=json.dumps(event("queued"))
        cases=(valid.encode(), valid+" "*8192, valid+"\x00", valid.replace('"queued"','"running"'),
               valid.replace('"queued"','"running", "state": "queued"'), "["*1500+"]"*1500)
        for raw in cases:
            with self.subTest(case=type(raw).__name__, size=len(raw)):
                s=EventStore(":memory:")
                try:
                    s.db.execute("INSERT INTO events(payload) VALUES (?)",(raw,))
                    for operation in (s.read, lambda:s.append(event("running")),
                                      lambda:s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc))):
                        with self.assertRaises(ValueError): operation()
                        self.assertFalse(s.db.in_transaction)
                        self.assertEqual(s.db.execute("SELECT count(*) FROM events").fetchone()[0],1)
                finally: s.close()

    def test_invalid_utf8_rejected(self):
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.db.execute("INSERT INTO events(payload) VALUES (CAST(X'FF' AS TEXT))")
        with self.assertRaises(ValueError): s.read()

    def test_read_enforces_count_cap(self):
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.append(event("queued"))
        s.append(event("running"))
        with patch("nexus_exchange.event_store.MAX_RECOVERY_EVENTS",1):
            with self.assertRaisesRegex(ValueError,"journal recovery capacity"): s.read()

    def test_maximum_unicode_event_survives_recovery(self):
        from datetime import datetime, timezone
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        raw=dict(event("queued"), task_id="🌱"*128,target="🌳"*256)
        s.append(raw)
        self.assertEqual(s.read(),(raw,))
        self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),1)
        self.assertEqual(s.read()[-1]["target"],raw["target"])

    def test_aggregate_limit_counts_utf8_bytes_on_all_paths(self):
        import json
        from datetime import datetime, timezone
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        first=dict(event("queued"),target="🌳"*100)
        second=dict(first,state="cancelled")
        raw=tuple(json.dumps(item,ensure_ascii=False,sort_keys=True) for item in (first,second))
        s.db.executemany("INSERT INTO events(payload) VALUES (?)", ((item,) for item in raw))
        size=sum(len(item.encode("utf-8")) for item in raw)
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES",size,create=True):
            self.assertEqual(s.read(),(first,second))
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES",size-1,create=True):
            for operation in (s.read,lambda:s.append(dict(event("queued"),task_id="b")),
                              lambda:s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc))):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError,"journal byte capacity"):
                        operation()
                    self.assertFalse(s.db.in_transaction)
                    self.assertEqual(tuple(row[0] for row in s.db.execute("SELECT payload FROM events ORDER BY seq")),raw)

    def test_byte_budget_reserves_recovery_at_exact_boundary(self):
        import json
        from datetime import datetime, timezone
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        first=dict(event("queued"),task_id="🌱"*128,target="🌳"*256)
        recovered=dict(first,state="interrupted",timestamp="2026-01-02T00:00:00.000000+00:00")
        size=sum(len(json.dumps(item,sort_keys=True).encode("utf-8")) for item in (first,recovered))
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES",size-1,create=True):
            with self.assertRaisesRegex(ValueError,"journal byte capacity"):
                s.append(first)
            self.assertEqual(s.read(),())
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES",size,create=True):
            s.append(first)
            with self.assertRaisesRegex(ValueError,"journal byte capacity"):
                s.append(dict(event("queued"),task_id="b"))
            self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),1)
            self.assertEqual(s.read(),(first,recovered))
            self.assertEqual(s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc)),0)

    def test_legacy_recovery_over_budget_holds_without_mutation(self):
        import json
        from datetime import datetime, timezone
        from unittest.mock import patch
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        first=event("queued")
        s.append(first)
        size=len(json.dumps(first,sort_keys=True).encode("utf-8"))
        s.db.execute("CREATE TRIGGER no_write BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'unexpected write'); END")
        with patch("nexus_exchange.event_store.MAX_JOURNAL_BYTES",size,create=True):
            self.assertEqual(s.read(),(first,))
            with self.assertRaisesRegex(ValueError,"journal byte capacity"):
                s.recover_interrupted(now=datetime(2026,1,2,tzinfo=timezone.utc))
            self.assertEqual(s.read(),(first,))
            self.assertFalse(s.db.in_transaction)

    def test_streamed_verification_detects_extra_row_and_rolls_back(self):
        s=EventStore(":memory:")
        self.addCleanup(s.close)
        s.append(event("queued"))
        s.db.execute("""CREATE TRIGGER extra_event AFTER INSERT ON events BEGIN
            INSERT INTO events(payload) VALUES (NEW.payload); END""")
        with self.assertRaisesRegex(ValueError,"journal mutation not persisted"):
            s.append(event("running"))
        self.assertEqual(s.read(),(event("queued"),))
        self.assertFalse(s.db.in_transaction)
