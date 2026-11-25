import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Event
from unittest.mock import patch
from desktop import archive_report, export_report, run_logged
from nexus_exchange.event_store import EventStore
from nexus_exchange.opportunity_archive import OpportunityArchive

class DesktopArchiveTests(unittest.TestCase):
    def test_run_reopen_search_export_and_rescreen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.sqlite3"
            events = EventStore(":memory:")
            try:
                with OpportunityArchive(path) as archive:
                    result = run_logged(events, archive=archive)
                now = datetime.now(timezone.utc)
                report = archive_report(path, now=now, query="SYNTHETIC")
                self.assertEqual(len(report["rows"]), 1)
                self.assertEqual(report["rows"][0]["key"], result[0].observation.opportunity.key)
                self.assertTrue(report["rows"][0]["eligible_for_review"])
                self.assertEqual(archive_report(path, now=now, query="absent")["rows"], [])
                later = archive_report(path, now=now+timedelta(days=9))
                self.assertFalse(later["rows"][0]["eligible_for_review"])
                self.assertIn("STALE_OBSERVATION", later["rows"][0]["reasons"])
                output = Path(directory) / "report.json"
                export_report(output, report)
                self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
                self.assertEqual(events.read()[-1]["state"], "succeeded")
            finally:
                events.close()

    def test_halted_task_does_not_archive(self):
        events = EventStore(":memory:")
        stop = Event()
        stop.set()
        try:
            with OpportunityArchive(":memory:") as archive:
                self.assertEqual(run_logged(events, stop, archive), ())
                self.assertEqual(archive.recent(now=datetime.now(timezone.utc)), ())
                self.assertEqual(events.read()[-1]["state"], "cancelled")
        finally:
            events.close()

    def test_archive_error_does_not_report_success(self):
        events = EventStore(":memory:")
        try:
            with OpportunityArchive(":memory:") as archive:
                with patch.object(archive, "record", side_effect=OSError("test")):
                    with self.assertRaises(OSError):
                        run_logged(events, archive=archive)
            self.assertEqual(events.read()[-1]["state"], "failed")
        finally:
            events.close()
