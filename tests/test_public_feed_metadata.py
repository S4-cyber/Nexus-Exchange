"""Owned wire fixtures for public feed representation and freshness metadata."""
from http.client import HTTPResponse
from io import BytesIO
import unittest
from unittest.mock import patch

from nexus_exchange import public_feeds


class FixtureSocket:
    def __init__(self, raw):
        self.raw = raw

    def makefile(self, *args, **kwargs):
        return BytesIO(self.raw)


def response_with(fields, status=b"200 OK"):
    response = HTTPResponse(FixtureSocket(
        b"HTTP/1.1 " + status + b"\r\nContent-Length: 2\r\n" + fields + b"\r\n{}"))
    response.begin()
    return response


class PublicFeedMetadataTests(unittest.TestCase):
    def test_partial_representation_rejected_before_read(self):
        for fields in (b"Content-Range: bytes 0-1/100\r\n",
                       b"Content-Range: bytes 0-1/2\r\n",
                       b"Content-Range: \r\n"):
            with self.subTest(fields=fields), patch.object(public_feeds, "build_opener") as opener:
                response = response_with(fields)
                opener.return_value.open.return_value = response
                with patch.object(response, "read", wraps=response.read) as reader:
                    with self.assertRaises(ValueError):
                        public_feeds.read_feed("canada")
                    reader.assert_not_called()
                self.assertTrue(response.isclosed())

    def test_malformed_headers_rejected_before_read(self):
        response = response_with(b"Malformed header\r\nContent-Range: bytes 0-1/100\r\n")
        self.assertTrue(response.headers.defects)
        with patch.object(public_feeds, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with patch.object(response, "read", wraps=response.read) as reader:
                with self.assertRaises(ValueError):
                    public_feeds.read_feed("canada")
                reader.assert_not_called()
        self.assertTrue(response.isclosed())

    def test_duplicate_last_modified_never_asserts_freshness(self):
        first = b"Last-Modified: Wed, 25 Nov 2026 12:00:00 GMT\r\n"
        second = b"Last-Modified: Mon, 23 Nov 2026 12:00:00 GMT\r\n"
        for fields in (first + second, second + first, first + first):
            with self.subTest(fields=fields), patch.object(public_feeds, "build_opener") as opener:
                opener.return_value.open.return_value = response_with(fields)
                self.assertEqual(public_feeds.read_feed("canada"), (200, b"{}", None))

    def test_single_or_missing_last_modified_preserved(self):
        stamp = "Wed, 25 Nov 2026 12:00:00 GMT"
        for fields, expected in ((b"Last-Modified: " + stamp.encode("ascii") + b"\r\n", stamp), (b"", None)):
            with self.subTest(fields=fields), patch.object(public_feeds, "build_opener") as opener:
                opener.return_value.open.return_value = response_with(fields)
                self.assertEqual(public_feeds.read_feed("canada"), (200, b"{}", expected))

    def test_non_success_does_not_consume_body(self):
        response = response_with(b"Content-Range: bytes 0-1/100\r\n", b"206 Partial Content")
        with patch.object(public_feeds, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with patch.object(response, "read", wraps=response.read) as reader:
                self.assertEqual(public_feeds.read_feed("canada"), (206, b"", None))
                reader.assert_not_called()
        self.assertTrue(response.isclosed())
