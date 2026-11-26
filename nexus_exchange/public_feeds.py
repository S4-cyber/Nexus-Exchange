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
            return response.status, response.read(adapter.MAX_BYTES + 1), response.headers.get("Last-Modified")
    except HTTPError as error:
        try:
            return error.code, b"", None
        finally:
            error.close()
