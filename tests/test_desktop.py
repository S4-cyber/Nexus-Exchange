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

    def test_pre_halted_task_is_cancelled(self):
        from threading import Event
        from unittest.mock import patch
        stop = Event()
        stop.set()
        store = EventStore(":memory:")
        try:
            with patch("desktop.demo") as demo:
                self.assertEqual(run_logged(store, stop), ())
                demo.assert_not_called()
            self.assertEqual([e["state"] for e in store.read()], ["queued", "cancelled"])
            self.assertEqual(project(store.read())["successful_tasks"], 0)
        finally:
            store.close()

    def test_halt_during_screening(self):
        from threading import Event
        from unittest.mock import patch
        stop = Event()
        def interrupt(**kwargs):
            stop.set()
            raise PermissionError("HALTED_OR_UNKNOWN")
        store = EventStore(":memory:")
        try:
            with patch("desktop.demo", side_effect=interrupt):
                self.assertEqual(run_logged(store, stop), ())
            self.assertEqual([e["state"] for e in store.read()], ["queued", "running", "cancelled"])
        finally:
            store.close()
