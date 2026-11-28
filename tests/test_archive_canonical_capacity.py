"""A readable legacy report must not be replaced by an unreadable archive."""
import json
import sqlite3
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from nexus_exchange.cycle_history import BRIEF, MAX_BYTES, CycleHistory, encode, latest


class ArchiveCanonicalCapacityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / BRIEF
        self.db = sqlite3.connect(self.root / 'events.sqlite3', isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)
        self.base = dict(format='nexus-engagement-brief-v1', status='Completed',
                         finished='2026-11-26T12:00:00+00:00', jobs={},
                         notes=[], sources=[], shortlist=[])

    def test_legacy_expansion_blocks_replacement_without_mutating_archive(self):
        prior = dict(self.base, notes=['prior'])
        self.history.publish(self.root, prior, lambda: None)
        self.history.publish(self.root, self.base, lambda: None)
        before = self.db.execute('SELECT * FROM cycle_briefs').fetchall()
        for notes in (['é' * (MAX_BYTES // 3)], [0] * (MAX_BYTES * 2 // 5)):
            with self.subTest(kind=type(notes[0]).__name__):
                legacy = dict(self.base, notes=notes)
                raw = json.dumps(legacy, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                self.assertLessEqual(len(raw), MAX_BYTES)
                self.assertGreater(len(encode(legacy)), MAX_BYTES)
                self.target.write_bytes(raw)
                self.assertEqual(latest(self.root), legacy)
                with self.assertRaisesRegex(ValueError, 'archive.*size limit'):
                    self.history.publish(self.root, self.base, lambda: None)
                self.assertEqual(self.target.read_bytes(), raw)
                self.assertEqual(self.db.execute('SELECT * FROM cycle_briefs').fetchall(), before)
                self.assertFalse(list(self.root.glob('.cycle-*.tmp')))

    def test_legacy_within_canonical_capacity_remains_archivable(self):
        legacy = dict(self.base, notes=['é' * (MAX_BYTES // 7)])
        raw = json.dumps(legacy, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.target.write_bytes(raw)
        canonical = encode(legacy)
        self.assertLessEqual(len(canonical), MAX_BYTES)
        self.history.publish(self.root, self.base, lambda: None)
        self.assertEqual(self.history.read(sha256(canonical).hexdigest()), legacy)
        self.assertEqual(latest(self.root), self.base)


if __name__ == '__main__':
    unittest.main()
