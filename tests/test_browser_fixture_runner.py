import unittest
from unittest.mock import patch
from copy import deepcopy

from nexus_exchange.browser_contract import FIXTURES, plan_fixture
from nexus_exchange.browser_fixture_runner import (
    FixtureDenied, _FixtureSession, _run_fixture, run_fixture,
)
from nexus_exchange.governor import Action, decide


class FixtureRunnerTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_fixture("procurement", halted=False)
        self.doc, self.css = FIXTURES["procurement"]

    def session(self, **kwargs):
        return _FixtureSession(self.plan, halted=False, **kwargs)

    def read(self, session, route=None, **kwargs):
        route = self.doc if route is None else route
        return session.read(route[0], **(dict(method="GET", resource=route[1],
                                               halted=False) | kwargs))

    def test_both_fixtures_with_real_clock(self):
        for fixture_id in FIXTURES:
            with self.subTest(fixture_id=fixture_id):
                report = run_fixture(plan_fixture(fixture_id, halted=False), halted=False)
                self.assertEqual(report["fixture_id"], fixture_id)
                self.assertEqual(report["attempts"], 2)
                self.assertEqual(report["trace"]["requests"], 2)
                self.assertEqual([a["resource"] for a in report["assets"]],
                                 ["document", "stylesheet"])
                for asset in report["assets"]:
                    self.assertEqual(len(asset["sha256"]), 64)
                    self.assertGreater(asset["size"], 0)
                for flag in ("independently_verified", "external_authority",
                             "network_enabled", "dispatch_enabled", "browser_executed"):
                    self.assertIs(report[flag], False)
        self.assertFalse(decide(Action.FETCH_EXTERNAL, halted=False).allowed)

    def test_deterministic_with_fixed_clock_and_no_raw_content(self):
        a = _run_fixture(self.plan, halted=False, clock=lambda: 123)
        b = _run_fixture(deepcopy(self.plan), halted=False, clock=lambda: 123)
        self.assertEqual(a, b)
        self.assertNotIn("Owned offline test fixture", repr(a))
        self.assertEqual(len(a["report_sha256"]), 64)

    def test_denial_before_asset_lookup_and_no_retry(self):
        s = self.session()
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            with self.assertRaises(FixtureDenied) as ctx:
                self.read(s, ("https://example.com/secret", "document", "text/html"))
            self.assertEqual(ctx.exception.attempts, 1)
            self.assertNotIn("secret", str(ctx.exception))
            with self.assertRaises(FixtureDenied):
                self.read(s)
            load.assert_not_called()
        self.assertTrue(s.closed)

    def test_wrong_method_and_malformed_inputs_never_load(self):
        for kwargs in ({"method": "POST"}, {"method": ["GET"]},
                       {"resource": "script"}, {"resource": []}):
            with self.subTest(kwargs=kwargs):
                s = self.session()
                with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
                    with self.assertRaises(FixtureDenied):
                        self.read(s, **kwargs)
                    load.assert_not_called()

    def test_request_budget_counts_failed_attempt(self):
        self.plan = plan_fixture("procurement", request_limit=1, halted=False)
        s = self.session()
        self.read(s)
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            with self.assertRaises(FixtureDenied) as ctx:
                self.read(s, self.css)
            self.assertEqual(ctx.exception.reason, "REQUEST_BUDGET_EXCEEDED")
            self.assertEqual(ctx.exception.attempts, 2)
            load.assert_not_called()

    def test_halt_before_execution_and_between_requests(self):
        for halted in (None, True, 0):
            with self.subTest(halted=halted):
                with self.assertRaises(PermissionError):
                    run_fixture(self.plan, halted=halted)
                s = self.session()
                self.read(s)
                with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
                    with self.assertRaises(FixtureDenied):
                        self.read(s, self.css, halted=halted)
                    load.assert_not_called()

    def test_deadline_before_lookup_and_after_lookup(self):
        self.plan = plan_fixture("procurement", timeout_ms=1, halted=False)
        s = self.session(clock=iter([0, 1_000_001]).__next__)
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            with self.assertRaises(FixtureDenied) as ctx:
                self.read(s)
            self.assertEqual(ctx.exception.reason, "DEADLINE_EXCEEDED")
            load.assert_not_called()
        s = self.session(clock=iter([0, 999_999, 1_000_001]).__next__)
        with self.assertRaises(FixtureDenied) as ctx:
            self.read(s)
        self.assertEqual(ctx.exception.reason, "DEADLINE_EXCEEDED")
        self.assertTrue(s.closed)

    def test_clock_regression_fails_closed(self):
        s = self.session(clock=iter([10, 9]).__next__)
        with self.assertRaises(FixtureDenied) as ctx:
            self.read(s)
        self.assertEqual(ctx.exception.reason, "CLOCK_INVALID")

    def test_no_replays_or_incomplete_success(self):
        s = self.session()
        with self.assertRaises(FixtureDenied):
            s.finish(halted=False)
        s = self.session()
        self.read(s)
        with self.assertRaises(FixtureDenied):
            self.read(s)
        s = self.session()
        self.read(s)
        self.read(s, self.css)
        s.finish(halted=False)
        with self.assertRaises(FixtureDenied):
            s.finish(halted=False)

    def test_response_validation_and_bounds(self):
        for asset in (("text/css", b"x"), ("text/html", b""),
                      ("text/html", b"x" * 4097), ("text/html", "not bytes")):
            with self.subTest(asset_type=type(asset[1])):
                with patch("nexus_exchange.browser_fixture_runner._load_asset",
                           return_value=asset):
                    with self.assertRaises(FixtureDenied):
                        self.read(self.session())

    def test_markup_cannot_invoke_script_or_form(self):
        for body in (b"<script>bad</script>", b"<form action='x'></form>",
                     b"<p onclick='x'>bad</p>", b"<img src='x'>",
                     b"<p>missing link</p>"):
            with self.subTest(body=body):
                with patch("nexus_exchange.browser_fixture_runner._load_asset",
                           return_value=("text/html", body)) as load:
                    with self.assertRaises(FixtureDenied) as ctx:
                        run_fixture(self.plan, halted=False)
                    self.assertEqual(ctx.exception.reason, "FIXTURE_MARKUP_DENIED")
                    self.assertEqual(load.call_count, 1)

    def test_parsed_off_origin_link_denied_before_lookup(self):
        body = b'<link rel="stylesheet" href="https://example.com/style.css">'
        with patch("nexus_exchange.browser_fixture_runner._load_asset",
                   return_value=("text/html", body)) as load:
            with self.assertRaises(FixtureDenied) as ctx:
                run_fixture(self.plan, halted=False)
            self.assertEqual(ctx.exception.reason, "RESOURCE_SCOPE_OR_ORDER_DENIED")
            self.assertEqual(load.call_count, 1)
            self.assertEqual(ctx.exception.attempts, 2)

    def test_tampered_plan_never_loads(self):
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            with self.assertRaises(ValueError):
                run_fixture(dict(self.plan, target="https://example.com/"), halted=False)
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
