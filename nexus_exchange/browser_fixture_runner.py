"""Owned, in-memory fixture transport for Scout browser research.

No socket, file, browser, subprocess, credentials, live URL or external dispatch.
The only public execution entry point runs one immutable synthetic fixture.
"""
from hashlib import sha256
from html.parser import HTMLParser
from time import monotonic_ns
from types import MappingProxyType

from .browser_contract import FIXTURES, _digest, _permit, validate_plan, review_trace

FORMAT = "nexus-fixture-run-v1"
MAX_ASSET_BYTES = 4096
_NS_PER_MS = 1_000_000


def _make_assets():
    assets = {}
    for fixture_id, label in (("procurement", "Synthetic procurement"),
                              ("digital_services", "Synthetic digital services")):
        document, style = FIXTURES[fixture_id]
        html = (
            '<html><head><title>' + label + '</title>'
            '<link rel="stylesheet" href="' + style[0] + '">'
            '</head><body><h1>' + label + '</h1>'
            '<p>Owned offline test fixture; not an actual opportunity.</p>'
            '</body></html>'
        ).encode("ascii")
        assets[document[0]] = (document[2], html)
        assets[style[0]] = (style[2], b"body { font-family: sans-serif; }")
    return MappingProxyType(assets)


_ASSETS = _make_assets()


class FixtureDenied(PermissionError):
    """Fixed reason code and attempt count; never echoes caller-supplied URLs."""
    def __init__(self, reason, attempts):
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts


def _load_asset(url):
    return _ASSETS[url]


class _FixtureSession:
    """Single-use internal transport, not an authorization or browser boundary."""
    def __init__(self, plan, *, halted=None, clock=monotonic_ns):
        self.plan = validate_plan(plan, halted=halted)
        self._clock = clock
        self._start = clock()
        if type(self._start) is not int or self._start < 0:
            raise FixtureDenied("CLOCK_INVALID", 0)
        self._last = self._start
        self.attempts = 0
        self.closed = False
        self._events = []
        self._assets = []

    def _fail(self, reason):
        self.closed = True
        raise FixtureDenied(reason, self.attempts)

    def _check(self, halted):
        if self.closed:
            self._fail("SESSION_CLOSED")
        try:
            _permit(halted)
        except PermissionError:
            self._fail("HALTED_OR_UNKNOWN")
        now = self._clock()
        if type(now) is not int or now < self._last:
            self._fail("CLOCK_INVALID")
        self._last = now
        delta = now - self._start
        if delta > self.plan["timeout_ms"] * _NS_PER_MS:
            self._fail("DEADLINE_EXCEEDED")
        return (delta + _NS_PER_MS - 1) // _NS_PER_MS

    def read(self, url, *, method, resource, halted=None):
        """Check policy BEFORE accessing the owned bytes; failure closes session."""
        if self.closed:
            self._fail("SESSION_CLOSED")
        self.attempts += 1
        self._check(halted)
        if self.attempts > self.plan["request_limit"]:
            self._fail("REQUEST_BUDGET_EXCEEDED")
        if type(method) is not str or method != "GET":
            self._fail("METHOD_DENIED")
        if (type(url) is not str or len(url) > 256
                or type(resource) is not str or len(resource) > 32):
            self._fail("RESOURCE_DENIED")
        routes = FIXTURES[self.plan["fixture_id"]]
        index = len(self._events)
        if index >= len(routes) or (url, resource) != routes[index][:2]:
            self._fail("RESOURCE_SCOPE_OR_ORDER_DENIED")
        try:
            media, body = _load_asset(url)
        except (KeyError, TypeError, ValueError):
            self._fail("FIXTURE_UNAVAILABLE")
        if (type(media) is not str or media != routes[index][2]
                or type(body) is not bytes or not 1 <= len(body) <= MAX_ASSET_BYTES):
            self._fail("FIXTURE_RESPONSE_DENIED")
        elapsed = self._check(halted)
        self._events.append(dict(url=url, method="GET", resource=resource,
                                 status=200, content_type=media, elapsed_ms=elapsed))
        self._assets.append(dict(resource=resource, size=len(body),
                                 sha256=sha256(body).hexdigest()))
        return body

    def finish(self, *, halted=None):
        """Only a complete two-resource fixture yields a report."""
        elapsed = self._check(halted)
        if len(self._events) != len(FIXTURES[self.plan["fixture_id"]]):
            self._fail("INCOMPLETE_FIXTURE")
        trace = review_trace(self.plan, self._events, halted=halted)
        payload = dict(format=FORMAT, fixture_id=self.plan["fixture_id"],
                       contract_sha256=self.plan["contract_sha256"],
                       attempts=self.attempts, elapsed_ms=elapsed,
                       assets=[dict(row) for row in self._assets],
                       trace=trace, result="OWNED_FIXTURE_COMPLETED",
                       independently_verified=False, external_authority=False,
                       network_enabled=False, dispatch_enabled=False,
                       browser_executed=False)
        self.closed = True
        return dict(payload, report_sha256=_digest(payload))


class _FixtureLinks(HTMLParser):
    """Recognize the one stylesheet reference in a trusted owned HTML fixture.

    Not a sanitizer for arbitrary external HTML. No rendering or script engine.
    """
    _tags = frozenset(("html", "head", "title", "body", "h1", "p", "link"))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag not in self._tags:
            raise ValueError("FIXTURE_MARKUP_DENIED")
        if tag == "link":
            if (len(attrs) != 2 or set(k for k, _ in attrs) != {"rel", "href"}
                    or dict(attrs)["rel"] != "stylesheet"
                    or type(dict(attrs)["href"]) is not str
                    or self.links):
                raise ValueError("FIXTURE_LINK_DENIED")
            self.links.append(dict(attrs)["href"])
        elif attrs:
            raise ValueError("FIXTURE_ATTRIBUTE_DENIED")

    def handle_endtag(self, tag):
        if tag not in self._tags or tag == "link":
            raise ValueError("FIXTURE_MARKUP_DENIED")

    def handle_startendtag(self, tag, attrs):
        if tag != "link":
            raise ValueError("FIXTURE_MARKUP_DENIED")
        self.handle_starttag(tag, attrs)

    def handle_decl(self, decl):
        raise ValueError("FIXTURE_MARKUP_DENIED")

    def handle_pi(self, data):
        raise ValueError("FIXTURE_MARKUP_DENIED")

    def unknown_decl(self, data):
        raise ValueError("FIXTURE_MARKUP_DENIED")


def _run_fixture(plan, *, halted=None, clock=monotonic_ns):
    session = _FixtureSession(plan, halted=halted, clock=clock)
    document = session.read(session.plan["target"], method="GET",
                            resource="document", halted=halted)
    parser = _FixtureLinks()
    try:
        parser.feed(document.decode("ascii"))
        parser.close()
        if len(parser.links) != 1:
            raise ValueError("FIXTURE_LINK_REQUIRED")
    except (ValueError, UnicodeError):
        session._fail("FIXTURE_MARKUP_DENIED")
    session.read(parser.links[0], method="GET", resource="stylesheet", halted=halted)
    return session.finish(halted=halted)


def run_fixture(plan, *, halted=None):
    """Run fixed local assets with an actual monotonic clock. No browser launched."""
    return _run_fixture(plan, halted=halted)
