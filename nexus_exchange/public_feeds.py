"""Bounded, credential-free requests to the two baseline public feeds via system proxies."""
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_feed(source, params=None):
    if source == "uk_tender" and type(params) is dict:
        from . import fts_search as adapter
        path = adapter.PATH + "?" + urlencode(params)
        timeout, accept = 10, "application/json"
    elif source == "canada" and params is None:
        from . import canada_search as adapter
        path = adapter.PATH
        timeout, accept = 15, "text/csv"
    else:
        raise ValueError("Unknown public feed.")
    url = "https://" + adapter.HOST + path
    request = Request(url, headers={"Accept": accept, "Accept-Encoding": "identity",
                                    "User-Agent": "NexusExchange-Preview/1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200:
                return response.status, b"", None
            return response.status, response.read(adapter.MAX_BYTES + 1), response.headers.get("Last-Modified")
    except HTTPError as error:
        try:
            return error.code, b"", None
        finally:
            error.close()
