"""Verify that the public transport admits only the fixed, bounded query."""
import unittest
from email.message import Message
from http.client import HTTPResponse, IncompleteRead
from io import BytesIO
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from nexus_exchange import public_feeds, fts_search, canada_search

def headers(**fields):
    result = Message()
    for name, value in fields.items():
        result[name.replace("_", "-")] = value
    return result


class FixtureSocket:
    def __init__(self, raw):
        self.raw = raw

    def makefile(self, *args, **kwargs):
        return BytesIO(self.raw)


def wire_response(header_lines, body):
    response = HTTPResponse(FixtureSocket(b"HTTP/1.1 200 OK\r\n" + header_lines + b"\r\n" + body))
    response.begin()
    return response


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
            response = MagicMock(status=200, headers=headers(Content_Length="2", Last_Modified="fixture"))
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
        response = MagicMock(status=200, headers=headers(Content_Length="13"))
        response.read.return_value = b"owned fixture"
        with patch.object(public_feeds, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value = response
            self.assertEqual(public_feeds.read_feed("canada"), (200, b"owned fixture", None))
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://" + canada_search.HOST + canada_search.PATH)
            response.read.assert_called_once_with(canada_search.MAX_BYTES + 1)

    def test_declared_length_truncation_is_not_a_complete_snapshot(self):
        # HTTPResponse.read(n) silently returns an early EOF for fixed-length
        # bodies. A complete-looking CSV prefix must not qualify as a dataset.
        body = b"reference,title\n1,Example\n"
        response = wire_response(b"Content-Length: 100\r\n", body)
        with patch.object(public_feeds, "build_opener") as factory:
            factory.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                public_feeds.read_feed("canada")
        self.assertTrue(response.isclosed())

    def test_ambiguous_or_unverifiable_framing_rejected_before_read(self):
        for field_lines in (b"", b"Content-Length: +2\r\n", b"Content-Length: 2, 2\r\n",
                            b"Content-Length: 2\r\nContent-Length: 2\r\n",
                            b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n",
                            b"Transfer-Encoding: gzip, chunked\r\n",
                            b"Transfer-Encoding: chunked \r\n",
                            b"Content-Length: 2\r\nContent-Encoding: gzip\r\n",
                            b"Content-Length: 999999999999999999999\r\n",
                            b"Content-Length: 2097153\r\n"):
            with self.subTest(header=field_lines), patch.object(public_feeds, "build_opener") as factory:
                payload = b"2\r\n{}\r\n0\r\n\r\n" if b"Transfer-Encoding: chunked" in field_lines else b"{}"
                response = wire_response(field_lines, payload)
                factory.return_value.open.return_value = response
                with patch.object(response, "read", wraps=response.read) as reader:
                    with self.assertRaises(ValueError):
                        public_feeds.read_feed("uk_tender", BASE)
                    reader.assert_not_called()
                self.assertTrue(response.isclosed())

    def test_complete_fixed_length_and_chunked_body_accepted(self):
        for framing, payload in ((b"Content-Length: 2\r\n", b"{}"),
                                 (b"Transfer-Encoding: chunked\r\n", b"2\r\n{}\r\n0\r\n\r\n")):
            with self.subTest(framing=framing), patch.object(public_feeds, "build_opener") as factory:
                response = wire_response(framing, payload)
                factory.return_value.open.return_value = response
                self.assertEqual(public_feeds.read_feed("uk_tender", BASE), (200, b"{}", None))
                self.assertTrue(response.isclosed())

    def test_chunked_body_exceeding_cap_is_rejected(self):
        response = wire_response(b"Transfer-Encoding: chunked\r\n", b"4\r\nabcd\r\n0\r\n\r\n")
        with patch.object(public_feeds, "build_opener") as factory, patch.object(fts_search, "MAX_BYTES", 3):
            factory.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                public_feeds.read_feed("uk_tender", BASE)
        self.assertTrue(response.isclosed())

    def test_interrupted_chunked_body_propagates_transport_failure(self):
        response = wire_response(b"Transfer-Encoding: chunked\r\n", b"2\r\n{}\r\n")
        with patch.object(public_feeds, "build_opener") as factory:
            factory.return_value.open.return_value = response
            with self.assertRaises(IncompleteRead):
                public_feeds.read_feed("uk_tender", BASE)
        self.assertTrue(response.isclosed())
