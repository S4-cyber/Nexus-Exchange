"""Read-only history snapshot tests with isolated synthetic receipt parsing."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from nexus_exchange import quote_history_store as store

PLAN = 'a'*64
KEY = 'b'*64
RAW = json.dumps([KEY, PLAN]).encode('ascii')


def inspect(data):
    key, plan = json.loads(data)
    return dict(receipt_sha256=key, plan_id=plan, scope_sha256='c'*64,
                snapshot_sha256='d'*64, rechecked_at='2026-11-27T00:00:00+00:00',
                historical_only=True, current_status='NOT_REVALIDATED',
                external_authority=False, execution_eligible=False)


class HistorySnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'history.sqlite3'
        parser = patch.object(store, 'inspect_receipt', side_effect=inspect)
        parser.start()
        self.addCleanup(parser.stop)
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            store.QuoteHistoryStore(db, permit=lambda: None).retain(PLAN, [RAW], confirmed=True)

    def verify(self):
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            self.assertIsNone(store.validate_history_snapshot(db))
            self.assertFalse(db.in_transaction)

    def test_closed_read_only_validation_preserves_bytes(self):
        before = self.path.read_bytes()
        self.verify()
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_extra_schema_and_missing_schema(self):
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute('CREATE TABLE unexpected(secret TEXT)')
            with self.assertRaises(ValueError):
                self.verify()
            db.execute('DROP TABLE unexpected')
            db.execute('DROP TABLE quote_history_v1')
            with self.assertRaises(ValueError):
                self.verify()

    def test_rejects_invalid_storage_identity_before_parser(self):
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            for value in ('x'*65536, b'a'*64, 'é'*64, 'f'*64):
                db.execute('UPDATE quote_history_v1 SET plan_id=?', (value,))
                with self.assertRaises(ValueError):
                    self.verify()
            db.execute('UPDATE quote_history_v1 SET plan_id=?', (PLAN,))
        self.verify()
