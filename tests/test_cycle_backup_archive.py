from hashlib import sha256
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from nexus_exchange import cycle_history as history


class ArchiveValidationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "events.sqlite3"
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.db.close)

    def row(self, index):
        brief = dict(format="nexus-engagement-brief-v1", status="Completed",
                     finished="2026-11-27T10:00:00+00:00", jobs={},
                     notes=[str(index)], shortlist=[], sources=[])
        body = history.encode(brief)
        return sha256(body).hexdigest(), brief["finished"], brief["status"], body

    def fill(self, count):
        history.CycleHistory(self.db)
        self.db.executemany("INSERT INTO cycle_briefs VALUES (?,?,?,?)",
                            (self.row(i) for i in range(count)))

    def validate(self):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            return history.validate_archive(db)

    def test_missing_archive_is_legacy_not_created(self):
        self.assertEqual(self.validate(), 0)
        self.assertEqual(self.db.execute("SELECT name FROM sqlite_master").fetchall(), [])

    def test_valid_full_archive_read_only(self):
        self.fill(history.KEEP_CYCLES)
        original = self.path.read_bytes()
        self.assertEqual(self.validate(), history.KEEP_CYCLES)
        self.assertEqual(self.path.read_bytes(), original)

    def test_oldest_row_not_hidden_by_display_limit(self):
        self.fill(history.KEEP_CYCLES)
        self.db.execute("UPDATE cycle_briefs SET status='forged' WHERE rowid=1")
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_over_capacity(self):
        self.fill(history.KEEP_CYCLES + 1)
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_malformed_body_even_with_matching_digest(self):
        self.fill(1)
        raw = b'{}'
        self.db.execute("UPDATE cycle_briefs SET body=?, digest=?", (raw, sha256(raw).hexdigest()))
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_invalid_digest_and_shadow_view(self):
        self.fill(1)
        self.db.execute("UPDATE cycle_briefs SET digest=?", ("x" * 64,))
        with self.assertRaises(ValueError):
            self.validate()
        self.db.execute("DROP TABLE cycle_briefs")
        self.db.execute("CREATE VIEW cycle_briefs AS SELECT 1")
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
