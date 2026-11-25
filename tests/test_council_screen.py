import unittest
from datetime import datetime, timezone, timedelta
from nexus_exchange.scout import normalize
from nexus_exchange.council_screen import screen

class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,1,2,tzinfo=timezone.utc)
        self.raw=dict(source="test",external_id="1",title="Fixture",source_url="https://example.org",retrieved_at="2026-01-01T23:00:00Z",deadline="2026-01-03T00:00:00Z",currency="USD",amount="100")
    def test_review_only(self):
        self.assertTrue(screen(normalize(self.raw),now=self.now).eligible_for_review)
    def test_stale(self):
        self.assertIn("STALE_OBSERVATION",screen(normalize(self.raw),now=self.now,max_age=timedelta(minutes=1)).reasons)
    def test_missing(self):
        self.raw.update(deadline=None,currency=None,amount=None)
        self.assertEqual(screen(normalize(self.raw),now=self.now).reasons,("MISSING_DEADLINE","MISSING_VALUE"))
    def test_expired(self):
        self.raw["deadline"]="2026-01-02T00:00:00Z"
        self.assertFalse(screen(normalize(self.raw),now=self.now).eligible_for_review)
