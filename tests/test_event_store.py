import tempfile
import unittest
from pathlib import Path
from nexus_exchange.event_store import EventStore

def event(state):
    return dict(task_id="a",target="fixture",state=state,timestamp="2026-01-01T00:00:00Z")

class StoreTests(unittest.TestCase):
    def test_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"events.db"
            s=EventStore(p)
            s.append(event("queued"))
            s.close()
            s=EventStore(p)
            try:
                s.append(event("running"))
                self.assertEqual(len(s.read()),2)
            finally: s.close()
    def test_rollback(self):
        s=EventStore(":memory:")
        try:
            s.append(event("queued"))
            with self.assertRaises(ValueError): s.append(event("succeeded"))
            self.assertEqual(s.read(),(event("queued"),))
        finally: s.close()
