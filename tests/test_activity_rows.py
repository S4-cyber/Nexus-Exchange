"""Synthetic SQLite fixtures for the read-only activity projection."""
import sqlite3
import unittest
from unittest.mock import patch

from nexus_exchange.activity_rows import read_scout_rows

STAMP = '2026-11-26T12:00:00+00:00'


class ActivityRowsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE scout_activity(item TEXT PRIMARY KEY, run TEXT, state TEXT, title TEXT, detail TEXT, stamp TEXT)')

    def insert(self, key='fixture', state='Finding', title='🌱', detail='Line 1\nLine 2', stamp=STAMP):
        self.db.execute('INSERT INTO scout_activity VALUES (?, ?, ?, ?, ?, ?)', (key, 'run', state, title, detail, stamp))

    def test_valid_unicode_and_legacy_timestamp_preserved(self):
        self.insert()
        self.assertEqual(read_scout_rows(self.db, {'Finding'}), [('fixture', 'Finding', '🌱', 'Line 1\nLine 2', STAMP)])

    def test_malformed_rows_are_rejected_without_mutating_database(self):
        cases = [dict(key='journal-fake'), dict(key='scout-activity-review-required'), dict(state='Unknown'),
                 dict(title='x'*513), dict(detail='x'*2049), dict(detail='private\x00fixture'),
                 dict(detail=b'raw bytes'), dict(stamp='2026-11-26T12:00:00'), dict(stamp='invalid')]
        for changes in cases:
            with self.subTest(changes=list(changes)):
                self.db.execute('DELETE FROM scout_activity')
                self.insert(**changes)
                before = self.db.total_changes
                with self.assertRaises(ValueError):
                    read_scout_rows(self.db, {'Finding'})
                self.assertEqual(self.db.total_changes, before)
                self.assertFalse(self.db.in_transaction)

    def test_invalid_utf8_is_controlled_rejection(self):
        self.insert()
        self.db.execute("UPDATE scout_activity SET title=CAST(X'FF' AS TEXT)")
        with self.assertRaises(ValueError):
            read_scout_rows(self.db, {'Finding'})

    def test_row_limit_rejects_instead_of_silently_truncating(self):
        self.insert()
        self.insert(key='second')
        with patch('nexus_exchange.activity_rows.MAX_ROWS', 1), self.assertRaises(ValueError):
            read_scout_rows(self.db, {'Finding'})

    def test_aggregate_limit_rejects_instead_of_silently_truncating(self):
        self.insert()
        self.insert(key='second')
        with patch('nexus_exchange.activity_rows.MAX_BYTES', 65), self.assertRaises(ValueError):
            read_scout_rows(self.db, {'Finding'})

    def test_non_utc_timestamp_normalized(self):
        self.insert(stamp='2026-11-26T13:00:00+01:00')
        self.assertEqual(read_scout_rows(self.db, {'Finding'})[0][4], STAMP)
