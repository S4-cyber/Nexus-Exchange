import sqlite3
import unittest
from contextlib import closing

from nexus_exchange import advisory_launch_marker as marker


class AdvisoryMarkerSnapshotTests(unittest.TestCase):
    def test_legacy_absence_and_valid_marker_are_read_only(self):
        with closing(sqlite3.connect(':memory:', isolation_level=None)) as db:
            self.assertFalse(marker.validate_snapshot(db))
            self.assertEqual(db.execute('SELECT name FROM sqlite_master').fetchall(), [])
            marker.initialize(db)
            self.assertFalse(marker.validate_snapshot(db))
            marker.arm(db, 'a' * 64)
            changes = db.total_changes
            db.execute('PRAGMA query_only=ON')
            self.assertTrue(marker.validate_snapshot(db))
            self.assertEqual(db.total_changes, changes)
            self.assertTrue(marker.pending(db))

    def test_trigger_rejected_even_when_empty_or_valid(self):
        with closing(sqlite3.connect(':memory:', isolation_level=None)) as db:
            marker.initialize(db)
            db.execute('CREATE TRIGGER broken AFTER INSERT ON advisory_launch_v1 '
                       'BEGIN DELETE FROM advisory_launch_v1; END')
            with self.assertRaisesRegex(ValueError, 'trigger'):
                marker.validate_snapshot(db)
            self.assertFalse(marker.pending(db))
            db.execute('DROP TRIGGER broken')
            marker.arm(db, 'b' * 64)
            db.execute('CREATE TRIGGER broken AFTER DELETE ON advisory_launch_v1 '
                       'BEGIN SELECT 1; END')
            with self.assertRaisesRegex(ValueError, 'trigger'):
                marker.validate_snapshot(db)
            self.assertTrue(marker.pending(db))

    def test_malformed_schema_rejected_even_without_rows(self):
        for schema in (
            'CREATE VIEW advisory_launch_v1 AS SELECT 1 AS slot, NULL AS reservation_id',
            'CREATE TABLE advisory_launch_v1(slot INTEGER, reservation_id TEXT)',
            'CREATE TABLE advisory_launch_v1(slot INTEGER PRIMARY KEY, reservation_id TEXT NOT NULL, extra TEXT)',
        ):
            with self.subTest(schema=schema), closing(sqlite3.connect(':memory:')) as db:
                db.execute(schema)
                with self.assertRaisesRegex(ValueError, 'schema'):
                    marker.validate_snapshot(db)

    def test_malformed_token_rejected_without_repair(self):
        with closing(sqlite3.connect(':memory:', isolation_level=None)) as db:
            marker.initialize(db)
            db.execute("INSERT INTO advisory_launch_v1 VALUES (1,'broken')")
            with self.assertRaisesRegex(ValueError, 'reservation'):
                marker.validate_snapshot(db)
            self.assertEqual(db.execute('SELECT reservation_id FROM advisory_launch_v1').fetchone(), ('broken',))


if __name__ == '__main__':
    unittest.main()
