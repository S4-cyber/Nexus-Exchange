"""Exercise bounded Scout activity admission and verified local writes."""
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from nexus_exchange.activity_feed import ActivityFeed, STATES
from nexus_exchange.activity_rows import read_scout_rows

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
ROW = ('fixture', 'Finding', 'Title', 'Detail')


class ActivityWriteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.feed = ActivityFeed(self.db)

    def stored(self):
        return self.db.execute('SELECT * FROM scout_activity ORDER BY item').fetchall()

    def test_invalid_inputs_do_not_persist_any_rows(self):
        cases = [('run', ('journal-fake', *ROW[1:]), NOW),
                 ('run', ('scout-activity-review-required', *ROW[1:]), NOW),
                 ('run', ('x'*513, *ROW[1:]), NOW),
                 ('run', (' ', *ROW[1:]), NOW),
                 ('run', ('second', 'Finding', 'bad\x00title', 'detail'), NOW),
                 ('run', ('second', 'Finding', b'raw', 'detail'), NOW),
                 ('run', ('second', 'Finding', 'bad\ud800', 'detail'), NOW),
                 ('run\x00', ROW, NOW), ('run', ROW, NOW.replace(tzinfo=None))]
        for run, bad, now in cases:
            with self.subTest(run=repr(run), key=bad[0][:20]):
                self.db.execute('DELETE FROM scout_activity')
                with self.assertRaises(ValueError):
                    self.feed.put(run, [ROW, bad], now)
                self.assertEqual(self.stored(), [])
                self.assertFalse(self.db.in_transaction)

    def test_bounded_generator_consumption_and_atomic_rejection(self):
        consumed = []
        def rows():
            for i in range(10):
                consumed.append(i)
                yield (str(i), *ROW[1:])
        with patch('nexus_exchange.activity_rows.MAX_ROWS', 2):
            with self.assertRaises(ValueError):
                self.feed.put('run', rows(), NOW)
        self.assertEqual(consumed, [0, 1, 2])
        self.assertEqual(self.stored(), [])
        with patch('nexus_exchange.activity_rows.MAX_BYTES', 1):
            with self.assertRaises(ValueError):
                self.feed.put('run', [ROW], NOW)
        self.assertEqual(self.stored(), [])

    def test_ignored_insert_rolls_back_entire_batch(self):
        self.db.execute("CREATE TRIGGER skip BEFORE INSERT ON scout_activity WHEN NEW.item='second' BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaises(ValueError):
            self.feed.put('run', [ROW, ('second', *ROW[1:])], NOW)
        self.assertEqual(self.stored(), [])
        self.assertFalse(self.db.in_transaction)

    def test_rewritten_insert_rolls_back_prior_state(self):
        self.feed.put('run', [ROW], NOW)
        before = self.stored()
        self.db.execute("CREATE TRIGGER rewrite AFTER INSERT ON scout_activity BEGIN UPDATE scout_activity SET state='Completed' WHERE item=NEW.item; END")
        with self.assertRaises(ValueError):
            self.feed.put('run', [('fixture', 'Finding', 'New', 'Detail')], NOW)
        self.assertEqual(self.stored(), before)
        self.assertFalse(self.db.in_transaction)

    def test_valid_truncation_and_last_write_wins_preserved(self):
        self.feed.put('run', [ROW, ('fixture', 'Completed', '🌱'*600, 'x'*3000)], NOW)
        row, = read_scout_rows(self.db, STATES)
        self.assertEqual(row[:4], ('fixture', 'Completed', '🌱'*512, 'x'*2048))
        self.assertEqual(row[4], NOW.isoformat())

    def test_duplicate_persisted_identity_rejected(self):
        self.db.execute('DROP TABLE scout_activity')
        self.db.execute('CREATE TABLE scout_activity(item TEXT, run TEXT, state TEXT, title TEXT, detail TEXT, stamp TEXT)')
        self.db.executemany('INSERT INTO scout_activity VALUES (?,?,?,?,?,?)',
                            [('fixture', 'run', 'Finding', 'one', '', NOW.isoformat()),
                             ('fixture', 'run', 'Completed', 'two', '', NOW.isoformat())])
        with self.assertRaises(ValueError):
            read_scout_rows(self.db, STATES)


if __name__ == '__main__':
    unittest.main()
