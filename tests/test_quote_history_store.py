"""Storage transaction tests with a deliberately isolated receipt parser."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nexus_exchange import quote_history_store as store

PLAN = 'a' * 64
OTHER = 'b' * 64


def raw(key='c', plan=PLAN):
    return json.dumps([key * 64, plan]).encode('ascii')


def inspect(data):
    key, plan = json.loads(data)
    return dict(receipt_sha256=key, plan_id=plan, scope_sha256='d'*64,
                snapshot_sha256='e'*64, rechecked_at='2026-11-27T00:00:00+00:00',
                historical_only=True, current_status='NOT_REVALIDATED',
                external_authority=False, execution_eligible=False)


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'history.sqlite'
        self.blocked = False
        self.parser = patch.object(store, 'inspect_receipt', side_effect=inspect)
        self.parser.start()
        self.addCleanup(self.parser.stop)
        self.open()

    def open(self):
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = store.QuoteHistoryStore(self.db, permit=self.permit)

    def permit(self):
        if self.blocked:
            raise PermissionError('halted')

    def test_restart_replay_and_exact_plan_deletion(self):
        self.history.retain(PLAN, [raw(), raw()], confirmed=True)
        self.history.retain(OTHER, [raw('f', OTHER)], confirmed=True)
        self.db.close()
        self.open()
        rows = self.history.list_plan(PLAN)
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]['execution_eligible'], False)
        with self.assertRaises(ValueError):
            self.history.forget(PLAN, ['f'*64], confirmed=True)
        self.history.forget(PLAN, ['c'*64], confirmed=True)
        self.assertEqual(self.history.list_plan(PLAN), [])
        self.assertEqual(len(self.history.list_plan(OTHER)), 1)

    def test_batch_atomicity_confirmation_and_capacity(self):
        with self.assertRaises(PermissionError):
            self.history.retain(PLAN, [raw()], confirmed=1)
        with self.assertRaises(ValueError):
            self.history.retain(PLAN, [raw(), raw('f', OTHER)], confirmed=True)
        self.assertEqual(self.history.list_plan(PLAN), [])
        with patch.object(store, 'MAX_INDEX_RECEIPTS', 1):
            self.history.retain(PLAN, [raw()], confirmed=True)
            with self.assertRaises(ValueError):
                self.history.retain(PLAN, [raw('f')], confirmed=True)
        self.assertEqual(len(self.history.list_plan(PLAN)), 1)
        with self.assertRaises(PermissionError):
            self.history.forget(PLAN, ['c'*64], confirmed=False)
        self.blocked = True
        with self.assertRaises(PermissionError):
            self.history.list_plan(PLAN)

    def test_shadow_trigger_and_tampered_row_fail_closed(self):
        self.history.retain(PLAN, [raw()], confirmed=True)
        self.db.execute('CREATE TEMP TABLE quote_history_v1(x)')
        with self.assertRaises(ValueError):
            self.history.list_plan(PLAN)
        self.db.execute('DROP TABLE temp.quote_history_v1')
        self.db.execute('CREATE TRIGGER block_delete BEFORE DELETE ON quote_history_v1 '
                        'BEGIN SELECT RAISE(IGNORE); END')
        with self.assertRaises(ValueError):
            self.history.forget(PLAN, ['c'*64], confirmed=True)
        self.db.execute('DROP TRIGGER block_delete')
        self.db.execute('UPDATE quote_history_v1 SET plan_id=?', (OTHER,))
        with self.assertRaises(ValueError):
            self.history.list_plan(OTHER)

    def test_halt_before_commit_rolls_back(self):
        calls = 0
        def permit():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError('halted')
        self.history.permit = permit
        with self.assertRaises(PermissionError):
            self.history.retain(PLAN, [raw()], confirmed=True)
        self.history.permit = self.permit
        self.assertEqual(self.history.list_plan(PLAN), [])
