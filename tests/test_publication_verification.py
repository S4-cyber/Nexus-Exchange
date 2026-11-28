"""Verify published bytes before reporting a successful Scout publication."""
import os
import sqlite3
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.cycle_history import BRIEF, CycleHistory, encode, latest


class PublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.db = sqlite3.connect(self.directory / 'events.sqlite3', isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)
        self.first = dict(format='nexus-engagement-brief-v1', status='Completed',
                          finished='2026-11-26T12:00:00+00:00', jobs={},
                          notes=['first'], shortlist=[], sources=[])
        self.second = dict(self.first, notes=['second'])
        self.target = self.directory / BRIEF
        self.history.publish(self.directory, self.first, lambda: None)

    def publish(self):
        return self.history.publish(self.directory, self.second, lambda: None)

    def test_noop_replacement_is_not_success(self):
        with patch('nexus_exchange.cycle_history.os.replace', return_value=None):
            with self.assertRaisesRegex(ValueError, 'publication verification'):
                self.publish()
        self.assertEqual(latest(self.directory), self.first)
        self.assertFalse(list(self.directory.glob('.cycle-*.tmp')))

    def test_changed_replacement_is_not_success_and_archive_survives(self):
        replace = os.replace
        def changed(source, dest):
            replace(source, dest)
            Path(dest).write_bytes(encode(dict(self.second, notes=['changed'])))
        with patch('nexus_exchange.cycle_history.os.replace', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'publication verification'):
                self.publish()
        self.assertEqual(self.history.read(sha256(encode(self.first)).hexdigest()), self.first)

    def test_sync_failure_keeps_old_report_and_does_not_archive(self):
        with patch('nexus_exchange.cycle_history.os.fsync', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(latest(self.directory), self.first)
        self.assertEqual(self.db.execute('SELECT count(*) FROM cycle_briefs').fetchone()[0], 0)
        self.assertFalse(list(self.directory.glob('.cycle-*.tmp')))

    def test_sync_precedes_replace_and_digest_matches_exact_bytes(self):
        fsync, replace = os.fsync, os.replace
        calls = []
        def sync(fd):
            calls.append('sync')
            fsync(fd)
        def swap(src, dst):
            calls.append('replace')
            replace(src, dst)
        with patch('nexus_exchange.cycle_history.os.fsync', side_effect=sync), \
                patch('nexus_exchange.cycle_history.os.replace', side_effect=swap):
            digest = self.publish()
        self.assertEqual(calls, ['sync', 'replace'])
        self.assertEqual(digest, sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(latest(self.directory), self.second)


if __name__ == '__main__':
    unittest.main()
