"""Verify the previous cycle is durably archived before replacing its report."""
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nexus_exchange.cycle_history import BRIEF, CycleHistory, encode, latest


class ArchiveAdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.db = sqlite3.connect(self.directory / 'events.sqlite3', isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)
        self.save(0)
        self.save(1)

    def brief(self, index):
        return dict(format='nexus-engagement-brief-v1', finished='2026-11-26T08:00:00+00:00',
                    status='Completed', notes=[str(index)], sources=[], shortlist=[], jobs={})

    def save(self, index):
        self.history.publish(self.directory, self.brief(index), lambda: None)

    def assert_rejected(self):
        original = (self.directory / BRIEF).read_bytes()
        before = self.db.execute('SELECT * FROM cycle_briefs ORDER BY rowid').fetchall()
        with self.assertRaises(ValueError):
            self.save(2)
        self.assertEqual((self.directory / BRIEF).read_bytes(), original)
        self.assertEqual(self.db.execute('SELECT * FROM cycle_briefs ORDER BY rowid').fetchall(), before)
        self.assertFalse(self.db.in_transaction)
        self.assertFalse(list(self.directory.glob('.cycle-*.tmp')))

    def test_ignored_archive_insert(self):
        self.db.execute('CREATE TRIGGER skip BEFORE INSERT ON cycle_briefs BEGIN SELECT RAISE(IGNORE); END')
        self.assert_rejected()

    def test_rewritten_archive_fields(self):
        for assignment in ("body=X'7B7D'", "status='Changed'", "finished='2025-01-01T00:00:00+00:00'"):
            with self.subTest(assignment=assignment):
                self.db.execute('CREATE TRIGGER rewrite AFTER INSERT ON cycle_briefs BEGIN '
                                'UPDATE cycle_briefs SET ' + assignment + ' WHERE digest=NEW.digest; END')
                try:
                    self.assert_rejected()
                finally:
                    self.db.execute('DROP TRIGGER rewrite')

    def test_corrupt_existing_digest_collision(self):
        raw = encode(self.brief(1))
        self.db.execute('INSERT INTO cycle_briefs VALUES (?,?,?,?)',
                        (sha256(raw).hexdigest(), self.brief(1)['finished'], 'Completed', b'{}'))
        self.assert_rejected()

    def test_ignored_retention(self):
        self.db.execute('CREATE TRIGGER skip BEFORE DELETE ON cycle_briefs BEGIN SELECT RAISE(IGNORE); END')
        with patch('nexus_exchange.cycle_history.KEEP_CYCLES', 1):
            self.assert_rejected()

    def test_retry_after_replace_failure_preserves_valid_archive(self):
        with patch('nexus_exchange.cycle_history.os.replace', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                self.save(2)
        self.save(2)
        self.assertEqual(latest(self.directory), self.brief(2))
        self.assertEqual(self.history.read(sha256(encode(self.brief(1))).hexdigest()), self.brief(1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM cycle_briefs').fetchone(), (2,))

    def test_retention_can_remove_oldest_and_preserve_previous(self):
        with patch('nexus_exchange.cycle_history.KEEP_CYCLES', 1):
            self.save(2)
        self.assertEqual(self.db.execute('SELECT digest FROM cycle_briefs').fetchall(),
                         [(sha256(encode(self.brief(1))).hexdigest(),)])
