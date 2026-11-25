import unittest
from copy import deepcopy

from nexus_exchange.browser_contract import (
    FIXTURES, MAX_ELAPSED_MS, MAX_REQUESTS, plan_fixture, validate_plan,
    review_trace,
)
from nexus_exchange.governor import Action, decide


class BrowserFixtureContractTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_fixture("procurement", halted=False)
        self.events = [
            self.event("procurement", 0, 30),
            self.event("procurement", 1, 60),
        ]

    @staticmethod
    def event(fixture_id, index, elapsed):
        url, resource, media = FIXTURES[fixture_id][index]
        return dict(url=url, method="GET", resource=resource, status=200,
                    content_type=media, elapsed_ms=elapsed)

    def review(self, events=None, plan=None):
        return review_trace(self.plan if plan is None else plan,
                            self.events if events is None else events,
                            halted=False)

    def test_deterministic_report_and_no_authority(self):
        report = self.review()
        self.assertEqual(report, self.review(deepcopy(self.events)))
        self.assertEqual(report["requests"], 2)
        self.assertEqual(report["elapsed_ms"], 60)
        for flag in ("external_authority", "network_enabled", "dispatch_enabled",
                     "browser_executed", "independently_verified"):
            self.assertIs(report[flag], False)
        self.assertFalse(decide(Action.FETCH_EXTERNAL, halted=False).allowed)

    def test_second_fixture_and_exact_one_request_budget(self):
        plan = plan_fixture("digital_services", request_limit=1,
                            timeout_ms=1, halted=False)
        report = self.review([self.event("digital_services", 0, 1)], plan)
        self.assertEqual(report["requests"], 1)
        self.assertEqual(report["elapsed_ms"], 1)

    def test_halt_and_unknown_halt_fail_closed(self):
        for halted in (None, True, 0, "false"):
            with self.subTest(halted=halted):
                for invoke in (
                    lambda: plan_fixture("procurement", halted=halted),
                    lambda: validate_plan(self.plan, halted=halted),
                    lambda: review_trace(self.plan, self.events, halted=halted),
                ):
                    with self.assertRaises(PermissionError):
                        invoke()

    def test_invalid_plan_parameters(self):
        for fixture_id in (None, [], "https://sam.gov/", "unknown"):
            with self.subTest(fixture_id=fixture_id), self.assertRaises(ValueError):
                plan_fixture(fixture_id, halted=False)
        for key, value in (("request_limit", True), ("request_limit", 0),
                           ("request_limit", MAX_REQUESTS + 1),
                           ("timeout_ms", False), ("timeout_ms", 0),
                           ("timeout_ms", MAX_ELAPSED_MS + 1)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                plan_fixture("procurement", halted=False, **{key: value})

    def test_plan_tampering_and_extra_fields(self):
        for key, value in (("external_authority", True), ("network_enabled", 0),
                           ("target", "https://example.com/"),
                           ("contract_sha256", "0" * 64), ("cookie", "fake"),
                           ("origin", "https://example.com/")):
            plan = dict(self.plan, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.review(plan=plan)

    def test_off_origin_and_ambiguous_url_rejected(self):
        target = self.events[0]["url"]
        urls = ("https://example.com/", "http://127.0.0.1/",
                target + "?token=x", target + "#fragment",
                target.replace("https://", "https://name@"),
                target.replace(".invalid", ".invalid:443"),
                target.replace("/index", "/%69ndex"),
                self.event("digital_services", 0, 30)["url"])
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.review([dict(self.events[0], url=url)])

    def test_writes_redirects_and_active_content_rejected(self):
        for key, value in (("method", "POST"), ("method", "HEAD"),
                           ("status", 301), ("status", 307), ("status", 404),
                           ("status", True), ("resource", "script"),
                           ("resource", "download"),
                           ("content_type", "application/octet-stream"),
                           ("content_type", "application/javascript")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.review([dict(self.events[0], **{key: value})])

    def test_extra_fields_and_malformed_events_rejected(self):
        for event in (None, [], {}, dict(self.events[0], cookie="x"),
                      dict(self.events[0], body="x"),
                      dict(self.events[0], url=["not a URL"]),
                      dict(self.events[0], elapsed_ms=True)):
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.review([event])

    def test_order_duplicate_and_cross_fixture_resource_rejected(self):
        for events in ([self.events[1], self.events[0]],
                       [self.events[0], self.events[0]],
                       [self.events[0], self.event("digital_services", 1, 60)]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.review(events)

    def test_request_budget_and_monotonic_elapsed(self):
        plan = plan_fixture("procurement", request_limit=1, halted=False)
        with self.assertRaises(ValueError):
            self.review(plan=plan)
        for events in ([], tuple(self.events),
                       [dict(self.events[0], elapsed_ms=-1)],
                       [dict(self.events[0], elapsed_ms=5001)],
                       [self.events[0], dict(self.events[1], elapsed_ms=29)]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                self.review(events)

    def test_optional_stylesheet_and_stable_trace_hash(self):
        first = self.review([self.events[0]])
        second = self.review()
        self.assertNotEqual(first["trace_sha256"], second["trace_sha256"])
        reordered = [dict(reversed(list(e.items()))) for e in self.events]
        self.assertEqual(second, self.review(reordered))


if __name__ == "__main__":
    unittest.main()
