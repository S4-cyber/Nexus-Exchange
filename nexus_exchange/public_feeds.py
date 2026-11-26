"""Bounded, credential-free requests to the two baseline public feeds via system proxies."""
from datetime import datetime, timedelta
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fts_parameters(params, page_size):
    """Accept only the typed adapter's bounded date window and opaque cursor."""
    required = {"updatedFrom", "updatedTo", "limit"}
    if (type(params) is not dict or any(type(k) is not str for k in params)
            or set(params) not in (required, required | {"cursor"})
            or any(type(v) is not str for v in params.values())
            or params["limit"] != str(page_size)):
        raise ValueError("Invalid public release query.")
    stamps = (params["updatedFrom"], params["updatedTo"])
    if any(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", s) is None
           for s in stamps):
        raise ValueError("Invalid public release date window.")
    try:
        start, end = map(datetime.fromisoformat, stamps)
    except ValueError:
        raise ValueError("Invalid public release date window.") from None
    if not timedelta(0) < end - start <= timedelta(days=7):
        raise ValueError("Invalid public release date window.")
    if "cursor" in params and re.fullmatch(r"[A-Za-z0-9_+/=-]{1,300}", params["cursor"]) is None:
        raise ValueError("Invalid public release cursor.")
    return {key: params[key] for key in ("updatedFrom", "updatedTo", "limit", "cursor") if key in params}


def _read_complete_body(response, cap):
    """Reject incomplete or ambiguous HTTP bodies before parsing source data."""
    lengths = response.headers.get_all("Content-Length", [])
    transfers = response.headers.get_all("Transfer-Encoding", [])
    encodings = response.headers.get_all("Content-Encoding", [])
    if encodings and (len(encodings) != 1 or encodings[0].strip().lower() != "identity"):
        raise ValueError("Unsupported public feed content encoding.")
    expected = None
    if transfers:
        if lengths or len(transfers) != 1 or transfers[0].lower() != "chunked":
            raise ValueError("Ambiguous public feed transfer framing.")
    else:
        # Close-delimited bodies cannot distinguish a complete snapshot from
        # a connection interrupted at an otherwise valid CSV row boundary.
        if len(lengths) != 1 or re.fullmatch(r"[0-9]{1,20}", lengths[0].strip()) is None:
            raise ValueError("Unverified public feed content length.")
        expected = int(lengths[0].strip())
        if expected > cap:
            raise ValueError("Public feed body exceeds cap.")
    body = response.read(cap + 1)
    if type(body) is not bytes or len(body) > cap or (expected is not None and len(body) != expected):
        raise ValueError("Incomplete or oversized public feed body.")
    return body


def read_feed(source, params=None):
    if source == "uk_tender" and type(params) is dict:
        from . import fts_search as adapter
        path = adapter.PATH + "?" + urlencode(_fts_parameters(params, adapter.PAGE_SIZE))
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
            return response.status, _read_complete_body(response, adapter.MAX_BYTES), response.headers.get("Last-Modified")
    except HTTPError as error:
        try:
            return error.code, b"", None
        finally:
            error.close()
