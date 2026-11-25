import tempfile
import unittest
from pathlib import Path
from desktop import run_logged
from nexus_exchange.event_store import EventStore
from nexus_exchange.dashboard_events import project

class DesktopTests(unittest.TestCase):
    def test_persistent_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            store = EventStore(path)
            try:
                self.assertTrue(run_logged(store)[0].screening.eligible_for_review)
            finally:
                store.close()
            store = EventStore(path)
            try:
                view = project(store.read())
                self.assertEqual(view["successful_tasks"], 1)
                self.assertEqual(len(view["history"]), 3)
            finally:
                store.close()
