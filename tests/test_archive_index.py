"""Historical index labels must not misrepresent stored report contents."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256

from nexus_exchange.cycle_history import CycleHistory, encode, latest


class ArchiveIndexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.db = sqlite3.connect(self.directory / 'events.sqlite3', isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)
        self.first = dict(format='nexus-engagement-brief-v1', status='Completed',
                          finished='2026-11-26T12:00:00+02:00', jobs={},
                          notes=['first'], shortlist=[], sources=[])
        self.history.publish(self.directory, self.first, lambda: None)
        self.second = dict(self.first, notes=['second'])
        self.history.publish(self.directory, self.second, lambda: None)
        self.key = sha256(encode(self.first)).hexdigest()

    def test_valid_index_uses_utc_and_read_matches(self):
        self.assertEqual(self.history.earlier(self.second),
                         [(self.key, '2026-11-26T10:00:00', 'Completed')])
        self.assertEqual(self.history.read(self.key), self.first)

    def test_metadata_mismatch_is_not_displayed_or_read(self):
        for column, changed in [('status', 'Sources unavailable'),
                                ('finished', '2026-11-26T13:00:00+00:00'),
                                ('status', sqlite3.Binary(b'Completed')),
                                ('status', 'x' * 300),
                                ('finished', 'bad')]:
            with self.subTest(column=column, changed=repr(changed)[:30]):
                self.db.execute('UPDATE cycle_briefs SET finished=?, status=?',
                                (self.first['finished'], self.first['status']))
                self.db.execute(f'UPDATE cycle_briefs SET {column}=?', (changed,))
                self.assertEqual(self.history.earlier(self.second),
                                 [(self.key, '', 'Archive entry needs review')])
                with self.assertRaises(ValueError):
                    self.history.read(self.key)
                self.assertEqual(latest(self.directory), self.second)

    def test_invalid_body_is_labelled_without_exposing_contents(self):
        self.db.execute('UPDATE cycle_briefs SET body=?', (b'private fixture',))
        self.assertEqual(self.history.earlier(self.second),
                         [(self.key, '', 'Archive entry needs review')])
        with self.assertRaises(ValueError):
            self.history.read(self.key)

    def test_invalid_digest_input_is_rejected(self):
        for key in (None, b'a'*64, 'a'*63, 'G'*64):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.history.read(key)


if __name__ == '__main__':
    unittest.main()
