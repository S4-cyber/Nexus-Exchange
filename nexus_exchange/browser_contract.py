"""Offline browser-harness contract and synthetic trace validator.

This module performs no network I/O, DNS lookup, browser launch or dispatch.
A passing trace is only a fixture-policy result, never live access permission.
"""
from hashlib import sha256
import json
from types import MappingProxyType

from .governor import Action, decide

FORMAT = "nexus-browser-fixture-v1"
ORIGIN = "https://nexus-scout.invalid"
FIXTURES = MappingProxyType({
    "procurement": (
        (ORIGIN + "/procurement/index.html", "document", "text/html"),
        (ORIGIN + "/procurement/style.css", "stylesheet", "text/css"),
    ),
    "digital_services": (
        (ORIGIN + "/services/index.html", "document", "text/html"),
        (ORIGIN + "/services/style.css", "stylesheet", "text/css"),
    ),
})
MAX_REQUESTS = 8
MAX_ELAPSED_MS = 15000
_EVENT_KEYS = frozenset(("url", "method", "resource", "status",
                         "content_type", "elapsed_ms"))


def _permit(halted):
    decision = decide(Action.SIMULATE, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def _bounded_int(value, low, high):
    return type(value) is int and low <= value <= high


def _digest(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    return sha256(raw).hexdigest()


def plan_fixture(fixture_id, *, request_limit=4, timeout_ms=5000, halted=None):
    """Create a fixed synthetic plan. No caller-supplied target URL."""
    _permit(halted)
    if type(fixture_id) is not str or fixture_id not in FIXTURES:
        raise ValueError("UNKNOWN_FIXTURE")
    if not _bounded_int(request_limit, 1, MAX_REQUESTS):
        raise ValueError("INVALID_REQUEST_LIMIT")
    if not _bounded_int(timeout_ms, 1, MAX_ELAPSED_MS):
        raise ValueError("INVALID_TIMEOUT")
    payload = dict(format=FORMAT, fixture_id=fixture_id, origin=ORIGIN,
                   target=FIXTURES[fixture_id][0][0],
                   request_limit=request_limit, timeout_ms=timeout_ms,
                   mode="SYNTHETIC_OFFLINE_ONLY", external_authority=False,
                   network_enabled=False, dispatch_enabled=False)
    return dict(payload, contract_sha256=_digest(payload))


def validate_plan(plan, *, halted=None):
    """Reconstruct the exact plan; its hash is not an authorization token."""
    _permit(halted)
    if type(plan) is not dict:
        raise ValueError("INVALID_PLAN")
    expected = plan_fixture(plan.get("fixture_id"),
                            request_limit=plan.get("request_limit"),
                            timeout_ms=plan.get("timeout_ms"), halted=halted)
    if set(plan) != set(expected):
        raise ValueError("PLAN_SCHEMA_MISMATCH")
    if any(type(plan[k]) is not type(v) or plan[k] != v
           for k, v in expected.items()):
        raise ValueError("PLAN_SCOPE_MISMATCH")
    return expected


def review_trace(plan, events, *, halted=None):
    """Check an offline trace against the fixed policy.

    Events are completion records in serial order from a synthetic fixture,
    not an authenticated network log or a browser pre-request interceptor.
    Only the exact first document and optional same-fixture stylesheet may
    appear. No arbitrary URLs, redirects, cookies, headers, bodies or scripts.
    """
    _permit(halted)
    checked = validate_plan(plan, halted=halted)
    if type(events) is not list or not 1 <= len(events) <= checked["request_limit"]:
        raise ValueError("REQUEST_BUDGET_OR_EMPTY_TRACE")
    entries = FIXTURES[checked["fixture_id"]]
    seen = set()
    previous = 0
    for index, event in enumerate(events):
        if type(event) is not dict or set(event) != _EVENT_KEYS:
            raise ValueError("EVENT_SCHEMA_MISMATCH")
        for key in ("url", "method", "resource", "content_type"):
            if type(event[key]) is not str or len(event[key]) > 256:
                raise ValueError("INVALID_EVENT_FIELD")
        if event["method"] != "GET":
            raise ValueError("METHOD_DENIED")
        if type(event["status"]) is not int or event["status"] != 200:
            raise ValueError("REDIRECT_OR_RESPONSE_DENIED")
        elapsed = event["elapsed_ms"]
        if not _bounded_int(elapsed, previous, checked["timeout_ms"]):
            raise ValueError("TIME_BUDGET_OR_ORDER")
        previous = elapsed
        key = (event["url"], event["resource"], event["content_type"])
        if index == 0 and key != entries[0]:
            raise ValueError("INITIAL_DOCUMENT_REQUIRED")
        if key not in entries or event["url"] in seen:
            raise ValueError("RESOURCE_SCOPE_OR_REPLAY_DENIED")
        seen.add(event["url"])
    # Canonical copy is bounded by the exact fixture fields above.
    normalized = [{k: event[k] for k in sorted(_EVENT_KEYS)} for event in events]
    payload = dict(format=FORMAT, contract_sha256=checked["contract_sha256"],
                   fixture_id=checked["fixture_id"], requests=len(events),
                   elapsed_ms=previous, trace_sha256=_digest(normalized),
                   result="FIXTURE_TRACE_POLICY_MATCH", independently_verified=False,
                   external_authority=False, network_enabled=False,
                   dispatch_enabled=False, browser_executed=False)
    return dict(payload, report_sha256=_digest(payload))
