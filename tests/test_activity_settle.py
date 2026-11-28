"""Synthetic interruption and retention failures must roll back together."""
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from nexus_exchange.activity_feed import ActivityFeed, STATES
from nexus_exchange.activity_rows import read_scout_rows

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)


class ActivitySettleTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.feed = ActivityFeed(self.db)
        self.feed.put('one', [('old', 'Finding', 'Old', ''),
                              ('active', 'Engaged', 'Work', '')], NOW)
        self.feed.put('two', [('other', 'Pending', 'Other', '')], NOW)

    def stored(self):
        return self.db.execute('SELECT * FROM scout_activity ORDER BY rowid DESC').fetchall()

    def assert_rollback(self, error=ValueError):
        before = self.stored()
        with patch('nexus_exchange.activity_feed.LIMIT', 1):
            with self.assertRaises(error):
                self.feed.settle('one', failed=True)
        self.assertEqual(self.stored(), before)
        self.assertFalse(self.db.in_transaction)

    def test_delete_failure_rolls_back_prior_settlement(self):
        self.db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON scout_activity BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        self.assert_rollback(sqlite3.IntegrityError)

    def test_ignored_update_rolls_back(self):
        self.db.execute("CREATE TRIGGER skip BEFORE UPDATE ON scout_activity BEGIN SELECT RAISE(IGNORE); END")
        self.assert_rollback()

    def test_ignored_retention_rolls_back(self):
        self.db.execute("CREATE TRIGGER skip BEFORE DELETE ON scout_activity BEGIN SELECT RAISE(IGNORE); END")
        self.assert_rollback()

    def test_valid_but_unexpected_rewrite_rolls_back(self):
        self.db.execute("CREATE TRIGGER rewrite AFTER UPDATE ON scout_activity BEGIN UPDATE scout_activity SET title='Changed' WHERE item='other'; END")
        self.assert_rollback()

    def test_scoped_settlement_preserves_other_run_and_retains_newest(self):
        with patch('nexus_exchange.activity_feed.LIMIT', 1):
            self.feed.settle('one', failed=True)
            before = self.stored()
            self.feed.settle('one', failed=True)
        self.assertEqual(self.stored(), before)
        self.assertEqual([(r[0], r[2]) for r in before],
                         [('other', 'Pending'), ('active', 'Needs attention')])
        self.assertEqual(len(read_scout_rows(self.db, STATES)), 2)

    def test_invalid_scope_does_not_change_rows(self):
        before = self.stored()
        for scope in ('', ' ', 'bad\x00scope', 1, 'x'*513):
            with self.subTest(scope=repr(scope)[:20]), self.assertRaises(ValueError):
                self.feed.settle(scope)
        with self.assertRaises(ValueError):
            self.feed.settle('one', failed='false')
        self.assertEqual(self.stored(), before)

    def test_admission_reserves_bytes_for_interruption(self):
        self.db.execute('DELETE FROM scout_activity')
        with patch('nexus_exchange.activity_rows.MAX_BYTES', 60):
            with self.assertRaisesRegex(ValueError, 'capacity'):
                self.feed.put('one', [('active', 'Engaged', 'Work', '')], NOW)
        self.assertEqual(self.stored(), [])


if __name__ == '__main__':
    unittest.main()
