import sqlite3
import tempfile
import unittest
from pathlib import Path

from nexus_exchange import advisory_launch_marker as marker


class AdvisoryLaunchMarkerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "events.sqlite3"
        self.token = "a" * 64

    def connect(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(db.close)
        return db

    def test_launch_marker_survives_connection_loss(self):
        db = self.connect()
        marker.initialize(db)
        self.assertFalse(marker.pending(db))
        marker.arm(db, self.token)
        db.close()
        reopened = self.connect()
        marker.initialize(reopened)
        self.assertTrue(marker.pending(reopened))
        with self.assertRaises(PermissionError):
            marker.arm(reopened, "b" * 64)

    def test_only_exact_reservation_can_clear(self):
        db = self.connect()
        marker.initialize(db)
        marker.arm(db, self.token)
        with self.assertRaises(PermissionError):
            marker.clear(db, "b" * 64)
        self.assertTrue(marker.pending(db))
        marker.clear(db, self.token)
        self.assertFalse(marker.pending(db))
        with self.assertRaises(PermissionError):
            marker.clear(db, self.token)

    def test_corrupt_state_is_not_empty(self):
        db = self.connect()
        marker.initialize(db)
        db.execute("INSERT INTO advisory_launch_v1 VALUES (1, 'invalid')")
        with self.assertRaises(ValueError):
            marker.pending(db)
        with self.assertRaises(ValueError):
            marker.clear(db, self.token)

    def test_no_uncommitted_arm_or_clear(self):
        db = self.connect()
        marker.initialize(db)
        db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(PermissionError):
            marker.arm(db, self.token)
        db.execute("ROLLBACK")
        marker.arm(db, self.token)
        db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(PermissionError):
            marker.clear(db, self.token)
        db.execute("ROLLBACK")
        self.assertTrue(marker.pending(db))
