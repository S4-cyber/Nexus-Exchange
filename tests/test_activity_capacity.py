"""Total persisted Scout activity must remain within the projection budget."""
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from nexus_exchange.activity_rows import read_scout_rows, write_scout_rows

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
STATES = {'Finding', 'Completed'}


class ActivityCapacityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE scout_activity(item TEXT PRIMARY KEY, run TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL, stamp TEXT NOT NULL)')

    def put(self, key, detail='detail', run='run', state='Finding'):
        write_scout_rows(self.db, run, [(key, state, 'title', detail)], NOW, STATES)

    def stored(self):
        return self.db.execute('SELECT * FROM scout_activity ORDER BY item').fetchall()

    def test_second_batch_over_total_row_capacity_rolls_back(self):
        with patch('nexus_exchange.activity_rows.MAX_ROWS', 1):
            self.put('one')
            before = self.stored()
            with self.assertRaisesRegex(ValueError, 'row capacity'):
                self.put('two')
            self.assertEqual(self.stored(), before)
            self.assertFalse(self.db.in_transaction)
            self.assertEqual(len(read_scout_rows(self.db, STATES)), 1)

    def test_second_batch_over_total_byte_capacity_rolls_back(self):
        with patch('nexus_exchange.activity_rows.MAX_BYTES', 100):
            self.put('one', '🌱'*10)
            before = self.stored()
            with self.assertRaisesRegex(ValueError, 'byte capacity'):
                self.put('two', '🌱'*10)
            self.assertEqual(self.stored(), before)
            self.assertFalse(self.db.in_transaction)

    def test_replacement_at_capacity_does_not_count_as_new_row(self):
        with patch('nexus_exchange.activity_rows.MAX_ROWS', 1):
            self.put('one')
            self.put('one', 'updated', state='Completed')
            self.assertEqual(read_scout_rows(self.db, STATES)[0][:4],
                             ('one', 'Completed', 'title', 'updated'))
            self.assertEqual(len(self.stored()), 1)

    def test_corrupted_existing_run_is_rejected_on_read_and_write(self):
        self.put('one')
        for expression in ("''", "CAST(X'FF' AS TEXT)", "X'726177'", "'bad' || char(0)"):
            with self.subTest(expression=expression):
                self.db.execute(f'UPDATE scout_activity SET run={expression}')
                with self.assertRaises(ValueError):
                    read_scout_rows(self.db, STATES)
                with self.assertRaises(ValueError):
                    self.put('two')
                self.assertEqual(self.db.execute('SELECT count(*) FROM scout_activity').fetchone(), (1,))
                self.assertFalse(self.db.in_transaction)

    def test_projection_counts_run_bytes(self):
        self.put('one', '', run='🌱'*20)
        with patch('nexus_exchange.activity_rows.MAX_BYTES', 100):
            with self.assertRaisesRegex(ValueError, 'byte capacity'):
                read_scout_rows(self.db, STATES)

    def test_final_scan_catches_corruption_of_non_target_row(self):
        self.put('one')
        before = self.stored()
        self.db.execute("CREATE TRIGGER damage AFTER INSERT ON scout_activity WHEN NEW.item='two' BEGIN UPDATE scout_activity SET detail=CAST(X'FF' AS TEXT) WHERE item='one'; END")
        with self.assertRaises(ValueError):
            self.put('two')
        self.assertEqual(self.stored(), before)
        self.assertFalse(self.db.in_transaction)


if __name__ == '__main__':
    unittest.main()
