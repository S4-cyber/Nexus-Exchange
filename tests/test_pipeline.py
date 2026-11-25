import unittest
from datetime import datetime, timezone
from nexus_exchange.pipeline import evaluate_snapshots

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.release = dict(ocid="ocds-test-1", id="r1", date="2026-01-01T00:00:00Z",
            tender=dict(status="active", title="Synthetic tender",
            tenderPeriod=dict(endDate="2026-02-01T00:00:00Z"),
            value=dict(amount=100,currency="USD")))
    def evaluate(self, halted=False, day=2):
        return evaluate_snapshots("test",[self.release],"https://example.org/data",
            "2026-01-02T00:00:00Z",now=datetime(2026,1,day,tzinfo=timezone.utc),halted=halted)
    def test_eligible(self):
        self.assertTrue(self.evaluate()[0].screening.eligible_for_review)
    def test_stale(self):
        self.assertIn("STALE_OBSERVATION",self.evaluate(day=4)[0].screening.reasons)
    def test_halted_or_unknown(self):
        for state in (True,None,0):
            with self.assertRaises(PermissionError): self.evaluate(halted=state)
    def test_invalid_batch(self):
        self.release["tender"]["status"]="cancelled"
        with self.assertRaises(ValueError): self.evaluate()
