import hashlib
import json
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from test_atlas import NOW, CODE, REGION, party
from test_economics import terms
from nexus_exchange.pipeline import evaluate_snapshots
from nexus_exchange.opportunity_archive import OpportunityArchive
from nexus_exchange.scenario_import import evaluate_scenario, FORMAT, MAX_BYTES

def observation(stamp=NOW):
    release=dict(ocid="ocds-example-1",id="compiled-1",date=(NOW-timedelta(days=1)).isoformat(),
        tender=dict(status="active",title="Synthetic tender",value=dict(amount=1000,currency="USD"),
            tenderPeriod=dict(endDate=(NOW+timedelta(days=7)).isoformat())))
    return evaluate_snapshots("test",[release],"https://example.org/source",stamp.isoformat(),
        now=stamp,halted=False)[0].observation

def manifest(item):
    return dict(format=FORMAT,opportunity_key=item.opportunity.key,
        retrieved_at=item.opportunity.retrieved_at.isoformat(),buyer=party("buyer","b1"),
        supplier=party("supplier","s1"),classifications=[dict(scheme=CODE[0],code=CODE[1])],
        region=REGION,terms=terms())

class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/"scenario.json"
        self.archive=Path(self.directory.name)/"archive.sqlite3"
        self.item=observation()
        with OpportunityArchive(self.archive) as archive:
            archive.record([self.item])

    def evaluate(self, data=None, **kwargs):
        raw=json.dumps(manifest(self.item) if data is None else data).encode()
        self.path.write_bytes(raw)
        return evaluate_scenario(self.path,self.archive,halted=False,now=kwargs.get("now",NOW))

    def test_report_roundtrip_and_digest(self):
        report=self.evaluate()
        self.assertEqual(report["input_sha256"],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(report["observation"]["opportunity"]["key"],self.item.opportunity.key)
        self.assertEqual(Decimal(report["assessment"]["expected_net"]),Decimal("40"))
        self.assertTrue(report["assessment"]["eligible_for_review"])
        self.assertFalse(report["assessment"]["external_authority"])
        self.assertEqual(json.loads(json.dumps(report)),report)

    def test_stale_evidence_cannot_qualify(self):
        report=self.evaluate(now=NOW+timedelta(days=2))
        self.assertFalse(report["assessment"]["eligible_for_review"])
        self.assertIn("OPPORTUNITY_STALE_OBSERVATION",report["assessment"]["reasons"])

    def test_superseded_snapshot_rejected(self):
        with OpportunityArchive(self.archive) as archive:
            archive.record([observation(NOW+timedelta(minutes=1))])
        with self.assertRaises(ValueError):
            self.evaluate(now=NOW+timedelta(minutes=1))

    def test_unknown_key_and_invalid_time(self):
        for changed in (dict(opportunity_key="a"*64),dict(retrieved_at="not-a-time"),
                        dict(format="unknown"),dict(extra=True)):
            data=manifest(self.item)
            data.update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                self.evaluate(data)

    def test_halt_before_file_read(self):
        with patch("nexus_exchange.scenario_import.Path.open") as opened:
            with self.assertRaises(PermissionError):
                evaluate_scenario(self.path,self.archive,halted=None,now=NOW)
            opened.assert_not_called()

    def test_oversize_duplicate_and_nonfinite_input(self):
        good=json.dumps(manifest(self.item))
        for raw in (b" "*(MAX_BYTES+1),good.replace('"format":','"format":"duplicate","format":').encode(),
                    good.replace('"exposure_limit": "100"','"exposure_limit": NaN').encode()):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                evaluate_scenario(self.path,self.archive,halted=False,now=NOW)

    def test_desktop_task_journal_and_export(self):
        from functools import partial
        from desktop import run_logged, export_report
        from nexus_exchange.event_store import EventStore
        from threading import Event
        self.path.write_text(json.dumps(manifest(self.item)),encoding="utf-8")
        events=EventStore(":memory:")
        try:
            work=partial(evaluate_scenario,self.path,self.archive,now=NOW)
            report=run_logged(events,work=work,target="Offline deal simulation")
            self.assertEqual(events.read()[-1]["state"],"succeeded")
            self.assertEqual(events.read()[-1]["target"],"Offline deal simulation")
            output=Path(self.directory.name)/"report.json"
            export_report(output,report)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")),report)
            stop=Event()
            stop.set()
            with patch("nexus_exchange.scenario_import.Path.open") as opened:
                self.assertEqual(run_logged(events,stop,work=work,target="Offline deal simulation"),())
                opened.assert_not_called()
            self.assertEqual(events.read()[-1]["state"],"cancelled")
        finally:
            events.close()
