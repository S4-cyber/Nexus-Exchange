import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from nexus_exchange.cycle_history import BRIEF, CycleHistory, KEEP_CYCLES, MAX_BYTES, latest


class CycleHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.db = sqlite3.connect(self.directory / "events.sqlite3", isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)

    def brief(self, index):
        return dict(format="nexus-engagement-brief-v1", finished="2026-11-25T08:00:00+00:00",
                    status="Completed", notes=[str(index)], sources=[], shortlist=[],
                    jobs=dict(produced=0, existing=0, held=0, full=False), external_actions=0)

    def save(self, index):
        self.history.publish(self.directory, self.brief(index), lambda: None)

    def test_upgrade_repeat_timestamps_retention_and_reopen(self):
        (self.directory / BRIEF).write_text(json.dumps(self.brief(0)))
        for n in range(1, KEEP_CYCLES + 3):
            self.save(n)
            if n == 1:
                (key, _, _), = self.history.earlier(latest(self.directory))
                self.assertEqual(self.history.read(key), self.brief(0))
        self.assertEqual(latest(self.directory), self.brief(KEEP_CYCLES + 2))
        db2 = sqlite3.connect(self.directory / "events.sqlite3")
        self.addCleanup(db2.close)
        reopened = CycleHistory(db2)
        earlier = reopened.earlier(latest(self.directory))
        self.assertEqual([reopened.read(key)["notes"][0] for key, _, _ in earlier],
                         [str(n) for n in range(KEEP_CYCLES + 1, 2, -1)])

    def test_cancelled_and_failed_replacement_leave_previous_history_intact(self):
        for i in range(3):
            self.save(i)
        original = latest(self.directory)
        before = self.history.earlier(original)
        with patch("nexus_exchange.cycle_history.os.replace", side_effect=OSError("busy")):
            with self.assertRaises(OSError):
                self.save(3)
        with self.assertRaises(PermissionError):
            def halt():
                raise PermissionError("halt")
            self.history.publish(self.directory, self.brief(4), halt)
        self.assertEqual(latest(self.directory), original)
        self.assertEqual(self.history.earlier(original), before)
        self.save(3)
        self.assertEqual(len(self.history.earlier(latest(self.directory))), 3)
        self.assertFalse(list(self.directory.glob(".cycle-*.tmp")))

    def test_malformed_legacy_brief_can_be_rebuilt_and_damaged_history_isolated(self):
        (self.directory / BRIEF).write_bytes(b" " * (MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            latest(self.directory)
        self.save(0)
        self.save(1)
        (key, _, _), = self.history.earlier(latest(self.directory))
        self.db.execute("UPDATE cycle_briefs SET body=?", (b"{}",))
        with self.assertRaises(ValueError):
            self.history.read(key)
        self.assertEqual(latest(self.directory), self.brief(1))
