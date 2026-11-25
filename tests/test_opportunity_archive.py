import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from nexus_exchange.opportunity_archive import OpportunityArchive
from nexus_exchange.pipeline import evaluate_snapshots

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)

def observation():
    release = dict(ocid="ocds-test-1", id="r1", date="2026-01-01T00:00:00Z",
        tender=dict(status="active", title="Synthetic tender",
        tenderPeriod=dict(endDate="2026-02-01T00:00:00Z"),
        value=dict(amount=123,currency="USD")))
    return evaluate_snapshots("test",[release],"https://example.org/data",
        NOW.isoformat(),now=NOW,halted=False)[0].observation

class ArchiveTests(unittest.TestCase):
    def test_restart_idempotency_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.sqlite3"
            item = observation()
            with OpportunityArchive(path) as archive:
                self.assertEqual(archive.record([item]), 1)
                self.assertEqual(archive.record([item]), 0)
            with OpportunityArchive(path) as archive:
                recent = archive.recent(now=NOW)
                self.assertEqual(recent[0].observation, item)
                self.assertTrue(recent[0].screening.eligible_for_review)
                later = archive.recent(now=NOW.replace(day=5))
                self.assertIn("STALE_OBSERVATION",later[0].screening.reasons)

    def test_conflict_rolls_back_entire_batch(self):
        item = observation()
        conflict = replace(item, opportunity=replace(item.opportunity,title="Different title"))
        with OpportunityArchive(":memory:") as archive:
            with self.assertRaises(ValueError):
                archive.record([item,conflict])
            self.assertEqual(archive.recent(now=NOW), ())

    def test_invalid_observation_and_bounds(self):
        item = observation()
        with OpportunityArchive(":memory:") as archive:
            for bad in (replace(item,release_key="bad"),
                        replace(item,published_at=NOW.replace(day=3)),
                        replace(item,opportunity=replace(item.opportunity,key="bad"))):
                with self.assertRaises(ValueError):
                    archive.record([bad])
            with self.assertRaises(ValueError):
                archive.recent(now=NOW,limit=101)
            self.assertEqual(archive.recent(now=NOW), ())
