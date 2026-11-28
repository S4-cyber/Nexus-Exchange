"""Owned SQLite fixtures for pre-worker startup recovery and maintenance."""
import sqlite3
import unittest
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nexus_exchange.activity_feed import (
    ActivityFeed, ActivityMaintenanceRequired, prepare_startup_activity,
)

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)


class ActivityStartupTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.halt = Event()
        self.guard = SimpleNamespace(events=SimpleNamespace(db=self.db),
                                     set=Mock(side_effect=self.halt.set))
        self.feed = ActivityFeed(self.db)
        self.feed.put('run', [('old', 'Finding', 'Existing notice', ''),
                              ('active', 'Engaged', 'Interrupted work', '')], NOW)

    def rows(self):
        return self.db.execute('SELECT * FROM scout_activity ORDER BY item').fetchall()

    def assert_maintenance(self):
        before = self.rows()
        with self.assertRaises(ActivityMaintenanceRequired) as error:
            prepare_startup_activity(self.guard)
        self.assertNotIn('fixture-secret', str(error.exception))
        self.assertTrue(self.halt.is_set())
        self.guard.set.assert_called_once_with()
        self.assertEqual(self.rows(), before)
        self.assertFalse(self.db.in_transaction)

    def test_valid_startup_settles_only_active_rows(self):
        before = dict((row[0], row) for row in self.rows())
        feed = prepare_startup_activity(self.guard)
        self.assertIsInstance(feed, ActivityFeed)
        after = dict((row[0], row) for row in self.rows())
        self.assertEqual(after['old'], before['old'])
        self.assertEqual(after['active'][2], 'Stopped')
        self.guard.set.assert_not_called()

    def test_invalid_legacy_state_requires_maintenance(self):
        self.db.execute("UPDATE scout_activity SET state='fixture-secret' WHERE item='old'")
        self.assert_maintenance()

    def test_oversized_legacy_projection_requires_maintenance(self):
        with patch('nexus_exchange.activity_rows.MAX_ROWS', 1):
            self.assert_maintenance()

    def test_ignored_recovery_requires_maintenance(self):
        self.db.execute('CREATE TRIGGER skip BEFORE UPDATE ON scout_activity '
                        'BEGIN SELECT RAISE(IGNORE); END')
        self.assert_maintenance()

    def test_database_error_does_not_leak_trigger_content(self):
        self.db.execute("CREATE TRIGGER fail BEFORE UPDATE ON scout_activity "
                        "BEGIN SELECT RAISE(ABORT, 'fixture-secret'); END")
        self.assert_maintenance()

    def test_halt_persistence_fault_cannot_admit_startup(self):
        self.db.execute("UPDATE scout_activity SET state='fixture-secret' WHERE item='old'")
        def fail_halt():
            self.halt.set()
            raise sqlite3.OperationalError('fixture-secret')
        self.guard.set.side_effect = fail_halt
        self.assert_maintenance()

    def test_incompatible_activity_schema_requires_maintenance(self):
        self.db.execute('DROP TABLE scout_activity')
        self.db.execute('CREATE TABLE scout_activity(item TEXT)')
        self.db.execute("INSERT INTO scout_activity VALUES ('preserve')")
        self.assert_maintenance()


if __name__ == '__main__':
    unittest.main()
