"""Actual SQLite regression fixtures for draft publication and local review."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.operator_drafts import DraftStore, prepare_rfq
from nexus_exchange.governor import Action, decide

NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)


class DraftPublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'operator.sqlite3'
        self.draft = prepare_rfq(dict(plan_id='a'*64, observation_sha256='b'*64,
            profile_revision='c'*64, supplier=dict(scheme='REGISTRY', identifier='SYNTHETIC'),
            region='US-CA', currency='USD', items=[dict(description='Synthetic task', quantity='1',
                unit='hour', classification=dict(scheme='NAICS', code='518210'))]), halted=False)
        self.key = self.draft['draft_id']

    def save(self, store):
        return store.save(self.draft, now=NOW, halted=False)

    def ack(self, store):
        return store.acknowledge(self.key, now=NOW+timedelta(seconds=1), confirmed=True, halted=False)

    def test_suppressed_insert_rejected_without_publication(self):
        with DraftStore(self.path) as store:
            store.db.execute('CREATE TRIGGER suppress BEFORE INSERT ON operator_drafts_v1 '
                             'BEGIN SELECT RAISE(IGNORE); END')
            with self.assertRaisesRegex(ValueError, 'unexpected draft storage trigger'):
                self.save(store)
            self.assertIsNone(store.get(self.key, halted=False))
            self.assertFalse(store.db.in_transaction)
            store.db.execute('DROP TRIGGER suppress')
            saved = self.save(store)
        with DraftStore(self.path, existing_only=True) as store:
            self.assertEqual(store.get(self.key, halted=False), saved)

    def test_suppressed_or_rewritten_ack_preserves_original(self):
        with DraftStore(self.path) as store:
            saved = self.save(store)
            for statement in (
                'CREATE TRIGGER bad BEFORE UPDATE ON operator_drafts_v1 BEGIN SELECT RAISE(IGNORE); END',
                "CREATE TRIGGER bad AFTER UPDATE ON operator_drafts_v1 BEGIN UPDATE operator_drafts_v1 SET payload='{}'; END",
                'CREATE TEMP TRIGGER bad AFTER UPDATE ON operator_drafts_v1 BEGIN DELETE FROM operator_drafts_v1; END',
            ):
                with self.subTest(statement=statement):
                    store.db.execute(statement)
                    try:
                        with self.assertRaisesRegex(ValueError, 'unexpected draft storage trigger'):
                            self.ack(store)
                        self.assertEqual(store.get(self.key, halted=False), saved)
                        self.assertFalse(store.db.in_transaction)
                    finally:
                        store.db.execute('DROP TRIGGER bad')
            reviewed = self.ack(store)
            self.assertFalse(reviewed['send_enabled'])
            self.assertFalse(reviewed['external_authority'])
            self.assertFalse(decide(Action.OUTREACH, halted=False).allowed)
        with DraftStore(self.path, existing_only=True) as store:
            self.assertEqual(store.get(self.key, halted=False), reviewed)

    def test_temp_shadow_cannot_supply_or_capture_records(self):
        with DraftStore(self.path) as store:
            saved = self.save(store)
            store.db.execute('CREATE TEMP TABLE operator_drafts_v1 AS SELECT * FROM main.operator_drafts_v1 WHERE 0')
            self.assertEqual(store.get(self.key, halted=False), saved)
            self.assertEqual(store.list_plan('a'*64, halted=False)['rows'], [saved])
            for operation in (self.save, self.ack):
                with self.assertRaisesRegex(ValueError, 'unexpected draft storage shadow'):
                    operation(store)
                self.assertFalse(store.db.in_transaction)
            self.assertEqual(store.db.execute('SELECT count(*) FROM temp.operator_drafts_v1').fetchone(), (0,))
            store.db.execute('DROP TABLE temp.operator_drafts_v1')
            self.assertEqual(store.get(self.key, halted=False), saved)

    def test_readback_independently_rolls_back_rewritten_update(self):
        with DraftStore(self.path) as store:
            saved = self.save(store)
            store.db.execute("CREATE TRIGGER bad AFTER UPDATE ON operator_drafts_v1 "
                             "BEGIN UPDATE operator_drafts_v1 SET payload='{}'; END")
            # Deliberately bypass the first line of defense to test readback independently.
            with patch.object(store, '_guard_write', return_value=None):
                with self.assertRaisesRegex(ValueError, 'draft storage integrity mismatch'):
                    self.ack(store)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(store.get(self.key, halted=False), saved)


if __name__ == '__main__':
    unittest.main()
