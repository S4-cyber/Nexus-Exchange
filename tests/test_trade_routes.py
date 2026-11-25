import unittest
from nexus_exchange.trade_routes import ROUTES, route_assessment

class RouteTests(unittest.TestCase):
    def test_unique_routes(self):
        self.assertEqual(len(ROUTES),17)
        self.assertEqual(len({r.key for r in ROUTES}),17)

    def test_all_routes_default_research_only(self):
        for route in ROUTES:
            r=route_assessment(route.key,halted=False)
            self.assertTrue(r["research_only"])
            self.assertFalse(r["external_authority"])
            self.assertFalse(r["execution_eligible"])
            self.assertFalse(r["zero_capital_verified"])
            self.assertIsNone(r["cash_exposure"])

    def test_regulated_brokerage_is_not_genesis(self):
        for key in ("real_estate","freight","customs","securities","credit","insurance"):
            r=route_assessment(key,halted=False)
            self.assertTrue(r["license_or_legal_review_required"])
            self.assertFalse(r["earned_revenue_candidate"])

    def test_grant_prize_and_asset_records_not_earned_opportunities(self):
        for key in ("grant","prize","asset_intel"):
            self.assertFalse(route_assessment(key,halted=False)["earned_revenue_candidate"])

    def test_unknown_and_halt(self):
        with self.assertRaises(ValueError):
            route_assessment("other",halted=False)
        with self.assertRaises(PermissionError):
            route_assessment("digital_service",halted=True)
