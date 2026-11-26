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

    def test_corrupt_marker_is_bounded_before_materialization(self):
        db = self.connect()
        marker.initialize(db)
        seen = []
        def decode(raw):
            seen.append(len(raw))
            return raw.decode("utf-8")
        db.text_factory = decode
        for value in ("a" * 65, "é" * 64, "a" * 64 + "\x00" + "x" * 8192,
                      b"a" * 64):
            with self.subTest(kind=type(value).__name__, size=len(value)):
                db.execute("DELETE FROM advisory_launch_v1")
                db.execute("INSERT INTO advisory_launch_v1 VALUES (1,?)", (value,))
                seen.clear()
                with self.assertRaises(ValueError):
                    marker.pending(db)
                with self.assertRaises(ValueError):
                    marker.clear(db, self.token)
                self.assertEqual(seen, [])
                self.assertEqual(db.execute("SELECT COUNT(*) FROM advisory_launch_v1").fetchone(), (1,))

    def test_invalid_utf8_is_rejected_without_clearing_marker(self):
        db = self.connect()
        marker.initialize(db)
        db.execute("INSERT INTO advisory_launch_v1 VALUES (1, CAST(? AS TEXT))", (b"\xff" * 64,))
        for operation in (lambda: marker.pending(db), lambda: marker.clear(db, self.token),
                          lambda: marker.arm(db, self.token)):
            with self.assertRaisesRegex(ValueError, "invalid advisory launch reservation"):
                operation()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM advisory_launch_v1").fetchone(), (1,))

    def test_ignored_arm_does_not_report_success(self):
        db = self.connect()
        marker.initialize(db)
        db.execute("""CREATE TRIGGER ignore_arm BEFORE INSERT ON advisory_launch_v1
                      BEGIN SELECT RAISE(IGNORE); END""")
        with self.assertRaises(PermissionError):
            marker.arm(db, self.token)
        self.assertFalse(db.in_transaction)
        self.assertFalse(marker.pending(self.connect()))

    def test_rewritten_arm_rolls_back(self):
        db = self.connect()
        marker.initialize(db)
        db.execute("""CREATE TRIGGER rewrite_arm AFTER INSERT ON advisory_launch_v1
                      BEGIN UPDATE advisory_launch_v1 SET reservation_id='""" + "b" * 64 + "'; END")
        with self.assertRaises(PermissionError):
            marker.arm(db, self.token)
        self.assertFalse(db.in_transaction)
        self.assertFalse(marker.pending(self.connect()))

    def test_ignored_clear_preserves_reservation(self):
        db = self.connect()
        marker.initialize(db)
        marker.arm(db, self.token)
        db.execute("""CREATE TRIGGER ignore_clear BEFORE DELETE ON advisory_launch_v1
                      BEGIN SELECT RAISE(IGNORE); END""")
        with self.assertRaises(PermissionError):
            marker.clear(db, self.token)
        self.assertFalse(db.in_transaction)
        self.assertEqual(marker._read(self.connect()), self.token)

    def test_reinserted_marker_rolls_back_clear(self):
        db = self.connect()
        marker.initialize(db)
        marker.arm(db, self.token)
        db.execute("""CREATE TRIGGER reinsert_clear AFTER DELETE ON advisory_launch_v1
                      BEGIN INSERT INTO advisory_launch_v1 VALUES(1,'""" + "b" * 64 + "'); END")
        with self.assertRaises(PermissionError):
            marker.clear(db, self.token)
        self.assertFalse(db.in_transaction)
        self.assertEqual(marker._read(self.connect()), self.token)
