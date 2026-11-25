import unittest
from decimal import Decimal
from nexus_exchange.ocds_adapter import map_active_tender

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.r = dict(ocid="ocds-test-1", id="r1", date="2026-01-01T00:00:00Z",
            tender=dict(status="active", title="Synthetic tender",
            tenderPeriod=dict(endDate="2026-02-01T00:00:00Z"),
            value=dict(amount=Decimal("100.25"),currency="USD")))
    def run_map(self):
        return map_active_tender("test",self.r,"https://example.org/data","2026-01-02T00:00:00Z")
    def test_mapping(self):
        self.assertEqual(self.run_map().opportunity.amount,Decimal("100.25"))
    def test_inactive(self):
        self.r["tender"]["status"]="cancelled"
        with self.assertRaises(ValueError): self.run_map()
    def test_expired(self):
        self.r["tender"]["tenderPeriod"]["endDate"]="2026-01-01T00:00:00Z"
        with self.assertRaises(ValueError): self.run_map()
    def test_float(self):
        self.r["tender"]["value"]["amount"]=100.25
        with self.assertRaises(ValueError): self.run_map()
    def test_future(self):
        self.r["date"]="2026-01-03T00:00:00Z"
        with self.assertRaises(ValueError): self.run_map()

    def test_integer_amount(self):
        self.r["tender"]["value"]["amount"]=100
        self.assertEqual(self.run_map().opportunity.amount,Decimal("100"))
