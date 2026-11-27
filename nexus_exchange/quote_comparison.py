"""Offline comparison of declared synthetic supplier quotations.

No extraction, network, ranking authority, acceptance or financial commitment.
A reference binds a declaration to a simulated reply, not to proven quote terms.
Callers must supply independently loaded local snapshots; hashes are not authentication.
"""
from datetime import datetime, timedelta

from .correspondence_thread import validate_thread
from .operator_drafts import _digest, _json, _shape, _stamp, _stored_stamp
from .governor import Action, decide

MAX_QUOTES = 16
MAX_CENTS = 99_999_999_999_999
_FIELDS = {"expected_head", "evidence_reference", "currency", "line_totals_cents",
           "tax_cents", "shipping_cents", "fees_cents", "delivery_days",
           "payment_days", "valid_until"}
_FLAGS = ("external_authority", "send_enabled", "recipient_verified",
          "reply_authenticated", "terms_verified", "execution_eligible",
          "commitment_enabled", "supplier_selected", "payment_authorized")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("bounded exact integer required")
    return value


def compare_quotes(entries, *, now, halted=None):
    """Compare equal RFQ baskets; withhold cost ranking for unequal declared terms.

    All line totals are explicitly declared extended USD cents, not unit prices.
    The caller must separately review completeness, availability and legal terms.
    This pure projection neither persists declarations nor verifies current runtime scope.
    """
    decision = decide(Action.EVALUATE, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    stamp = _stamp(now)
    if type(entries) is not list or not 2 <= len(entries) <= MAX_QUOTES:
        raise ValueError("two to sixteen quotation declarations required")
    scope = None
    rows = []
    suppliers, evidence = set(), set()
    for entry in entries:
        _shape(entry, {"draft", "recipient", "thread", "declaration"})
        draft = entry["draft"]
        thread = validate_thread(draft, entry["recipient"], entry["thread"], halted=False)
        request = draft["request"]
        basket = {k: request[k] for k in ("plan_id", "observation_sha256",
                  "profile_revision", "region", "currency", "items")}
        if scope is None:
            scope = basket
        elif basket != scope:
            raise ValueError("quotation RFQ baskets or source scopes differ")
        supplier = request["supplier"]
        party = (supplier["scheme"], supplier["identifier"])
        if party in suppliers:
            raise ValueError("duplicate declared supplier identity")
        suppliers.add(party)
        raw = entry["declaration"]
        _shape(raw, _FIELDS)
        events = thread["events"]
        if (not events or events[-1]["kind"] != "SIMULATED_REPLY"
                or raw["expected_head"] != thread["head_sha256"]
                or raw["evidence_reference"] != events[-1]["evidence_reference"]):
            raise ValueError("exact latest simulated reply reference required")
        event = events[-1]
        if event["recorded_at"] > stamp:
            raise ValueError("future-dated simulated reply")
        reference = event["evidence_reference"]
        if reference in evidence:
            raise ValueError("duplicate simulated reply evidence")
        evidence.add(reference)
        valid = _stored_stamp(raw["valid_until"])
        if valid <= stamp or datetime.fromisoformat(valid) - now > timedelta(days=365):
            raise ValueError("expired or excessively distant declared quote validity")
        if raw["currency"] != "USD":
            raise ValueError("USD-only quotation comparison")
        line_totals = raw["line_totals_cents"]
        if type(line_totals) is not list or len(line_totals) != len(request["items"]):
            raise ValueError("exact RFQ line coverage required")
        lines = [_integer(x, 0, MAX_CENTS) for x in line_totals]
        extra = {k: _integer(raw[k], 0, MAX_CENTS)
                 for k in ("tax_cents", "shipping_cents", "fees_cents")}
        total = _integer(sum(lines) + sum(extra.values()), 1, MAX_CENTS)
        terms = {k: _integer(raw[k], 0, 3650) for k in ("delivery_days", "payment_days")}
        payload = dict(draft_id=draft["draft_id"], recipient_id=thread["recipient_id"],
                       supplier=dict(supplier), thread_id=thread["thread_id"],
                       reply_sha256=thread["head_sha256"], evidence_reference=reference,
                       valid_until=valid, currency="USD", line_totals_cents=lines,
                       total_cents=total, **extra, **terms)
        rows.append(dict(payload, declaration_sha256=_digest(_json(payload))))
    equal_terms = len({(r["delivery_days"], r["payment_days"]) for r in rows}) == 1
    rows.sort(key=lambda r: (r["total_cents"] if equal_terms else 0,
                            r["declaration_sha256"]))
    minimum = rows[0]["total_cents"] if equal_terms else None
    result = dict(format="nexus-synthetic-quote-comparison-v1",
                  mode="SIMULATION_ONLY", compared_at=stamp,
                  scope_sha256=_digest(_json(scope)), plan_id=scope["plan_id"],
                  equal_declared_timing=equal_terms,
                  status="DECLARED_COST_ORDER_ONLY" if equal_terms else "DIFFERENT_TIMING_REVIEW",
                  rows=rows, lowest_declared_total_cents=minimum,
                  lowest_declared_cost_ids=[r["declaration_sha256"] for r in rows
                                            if equal_terms and r["total_cents"] == minimum],
                  **dict.fromkeys(_FLAGS, False))
    return dict(result, comparison_sha256=_digest(_json(result)))
