import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from nexus_exchange.local_import import evaluate_file, FORMAT, MAX_BYTES

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)

def manifest():
    return dict(format=FORMAT,publisher="test-publisher",source_url="https://example.org/data",
        retrieved_at="2026-01-02T00:00:00Z",releases=[
        dict(ocid="ocds-test-1",id="compiled-1",date="2026-01-01T00:00:00Z",tag=["compiled"],
            tender=dict(status="active",title="Example tender",value=dict(amount=100,currency="USD"),
                tenderPeriod=dict(endDate="2026-02-01T00:00:00Z")))])

class ImportTests(unittest.TestCase):
    def evaluate(self, raw, halted=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_bytes(raw)
            return evaluate_file(path,halted=halted,now=NOW)

    def test_valid_compiled_snapshot(self):
        result=self.evaluate(json.dumps(manifest()).encode())
        self.assertEqual(len(result),1)
        self.assertTrue(result[0].screening.eligible_for_review)
        self.assertEqual(result[0].observation.opportunity.source_url,"https://example.org/data")

    def test_exact_decimal(self):
        raw=json.dumps(manifest()).replace('"amount": 100','"amount": 100.1234')
        result=self.evaluate(raw.encode())
        self.assertEqual(str(result[0].observation.opportunity.amount),"100.1234")

    def test_halt_precedes_file_read(self):
        with patch("nexus_exchange.local_import.Path.open") as opened:
            with self.assertRaises(PermissionError):
                evaluate_file("missing.json",halted=True,now=NOW)
            opened.assert_not_called()

    def test_reject_invalid_payloads(self):
        raw=json.dumps(manifest())
        for bad in (raw.replace('"compiled"','"tenderUpdate"'),
                    raw.replace('"amount": 100','"amount": 1e1000000'),
                    raw.replace('"amount": 100','"amount": NaN'),
                    raw.replace('"amount": 100','"amount": 100, "amount": 200'),
                    raw.replace("https://example.org/data","http://example.org/data"),
                    raw.replace("2026-01-02T00:00:00Z","2026-01-03T00:00:00Z")):
            with self.subTest(payload=bad):
                with self.assertRaises(ValueError):
                    self.evaluate(bad.encode())

    def test_size_limit(self):
        with self.assertRaises(ValueError):
            self.evaluate(b" "*(MAX_BYTES+1))

    def test_empty_and_oversized_batch(self):
        for length in (0,101):
            m=manifest()
            m["releases"]*=length
            with self.assertRaises(ValueError):
                self.evaluate(json.dumps(m).encode())

    def test_desktop_workflow_archives_import(self):
        from functools import partial
        from desktop import run_logged
        from nexus_exchange.event_store import EventStore
        from nexus_exchange.opportunity_archive import OpportunityArchive
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(manifest()),encoding="utf-8")
            events = EventStore(":memory:")
            try:
                with OpportunityArchive(":memory:") as archive:
                    result = run_logged(events,archive=archive,
                        work=partial(evaluate_file,path,now=NOW),target="Local compiled snapshot import")
                    self.assertEqual(archive.recent(now=NOW)[0].observation,result[0].observation)
                    self.assertEqual(events.read()[-1]["state"],"succeeded")
                    self.assertEqual(events.read()[-1]["target"],"Local compiled snapshot import")
            finally:
                events.close()
