"""Verify that the public transport admits only the fixed, bounded query."""
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from nexus_exchange import public_feeds, fts_search, canada_search

BASE = dict(updatedFrom="2026-11-24T12:00:00", updatedTo="2026-11-25T12:00:00", limit="25")


class PublicFeedTests(unittest.TestCase):
    def test_unapproved_parameters_never_reach_transport(self):
        for extra in ({"api_key": "synthetic"}, {"url": "https://example.invalid"},
                      {"limit": "1000"}, {"limit": 25}, {"cursor": "https://example.invalid"},
                      {"cursor": "x" * 301}, {"cursor": ["a", "b"]},
                      {"updatedFrom": "2026-11-01T12:00:00"},
                      {"updatedFrom": "2026-11-25T12:00:00"},
                      {"updatedTo": "2026-11-25T12:00:00+00:00"}):
            with self.subTest(fields=tuple(extra)), patch.object(public_feeds, "build_opener") as opener:
                with self.assertRaises(ValueError):
                    public_feeds.read_feed("uk_tender", dict(BASE, **extra))
                opener.assert_not_called()

    def test_incomplete_or_unexpected_route_never_opens(self):
        missing = dict(BASE)
        del missing["updatedFrom"]
        with patch.object(public_feeds, "build_opener") as opener:
            for source, params in (("uk_tender", missing), ("canada", {}), ("other", None)):
                with self.subTest(source=source), self.assertRaises(ValueError):
                    public_feeds.read_feed(source, params)
            opener.assert_not_called()

    def test_fixed_route_and_opaque_cursor_preserved(self):
        for params in (BASE, dict(BASE, cursor="ab+/=")):
            response = MagicMock(status=200, headers={"Last-Modified": "fixture"})
            response.read.return_value = b"{}"
            with self.subTest(cursor=params.get("cursor")), patch.object(public_feeds, "build_opener") as factory:
                factory.return_value.open.return_value.__enter__.return_value = response
                self.assertEqual(public_feeds.read_feed("uk_tender", params), (200, b"{}", "fixture"))
                request = factory.return_value.open.call_args.args[0]
                parsed = urlsplit(request.full_url)
                self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", fts_search.HOST, fts_search.PATH))
                self.assertEqual(parse_qs(parsed.query), {k: [v] for k, v in params.items()})
                response.read.assert_called_once_with(fts_search.MAX_BYTES + 1)

    def test_canada_stays_parameter_free(self):
        response = MagicMock(status=200, headers={})
        response.read.return_value = b"owned fixture"
        with patch.object(public_feeds, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value = response
            self.assertEqual(public_feeds.read_feed("canada"), (200, b"owned fixture", None))
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://" + canada_search.HOST + canada_search.PATH)
            response.read.assert_called_once_with(canada_search.MAX_BYTES + 1)
