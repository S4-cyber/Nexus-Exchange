"""Bounded historical quotation receipts; not a current decision or permission."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile

from .operator_drafts import MAX_ITEMS, _digest, _hash, _json, _scheme, _shape, _stored_stamp, _text
from .quote_comparison import MAX_QUOTES, MAX_CENTS, _FLAGS, _integer
from .evidence import parse_reference
from .governor import Action, decide
from .quote_history_lineage import MAX_INDEX_RECEIPTS, annotate_history

MAX_RECEIPT_BYTES = 64 * 1024


def _projection(result):
    if type(result) is not dict or result.get("format") != "nexus-synthetic-quote-comparison-v1":
        raise ValueError("reviewed synthetic comparison required")
    if result.get("mode") != "SIMULATION_ONLY" or any(result.get(k) is not False for k in _FLAGS):
        raise ValueError("historical authority mismatch")
    _stored_stamp(result.get("compared_at"))
    key = _hash(result.get("comparison_sha256"))
    payload = {k: v for k, v in result.items() if k != "comparison_sha256"}
    if _digest(_json(payload)) != key:
        raise ValueError("comparison digest mismatch")
    return _json({k: v for k, v in payload.items() if k != "compared_at"})


def historical_receipt(reviewed, current):
    """Both inputs must come from independently recomputed local comparisons.

    A digest is integrity metadata, not proof of authenticity. No raw reply
    content, recipient addresses, supplier profiles or filesystem paths added.
    """
    if _projection(reviewed) != _projection(current):
        raise ValueError("quotation evidence changed; review again")
    if datetime.fromisoformat(current["compared_at"]) < datetime.fromisoformat(reviewed["compared_at"]):
        raise ValueError("comparison clock moved backwards")
    payload = dict(format="nexus-historical-quote-review-v1",
                   historical_only=True, current_decision=False,
                   external_authority=False, execution_eligible=False,
                   rechecked_at=current["compared_at"],
                   rechecked_comparison_sha256=current["comparison_sha256"],
                   comparison=deepcopy(reviewed))
    return dict(payload, receipt_sha256=_digest(_json(payload)))


def publish_receipt(path, receipt, *, permit):
    """Publish closed, fsynced bytes under a new local JSON filename.

    No overwrite fallback. A halt after publication may leave a complete file
    without a returned success. Never remove the destination on failure.
    """
    permit()
    raw = os.fspath(path)
    if (type(raw) is not str or not os.path.isabs(raw) or len(raw) > 4096
            or raw.startswith(("//", "\\\\")) or any(ord(c) < 32 for c in raw)):
        raise ValueError("select an absolute local JSON path")
    target = Path(raw)
    if (target.suffix.lower() != ".json" or ".." in target.parts or ":" in target.name
            or PureWindowsPath(target.name).is_reserved()
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError("select a new JSON file in an existing direct directory")
    data = (_json(receipt) + "\n").encode("ascii")
    if not 1 <= len(data) <= MAX_RECEIPT_BYTES:
        raise ValueError("historical receipt exceeds export budget")
    temporary = None
    try:
        if os.path.lexists(target):
            raise FileExistsError("history destination exists")
        fd, name = tempfile.mkstemp(prefix=".nexus-quote-", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as output:
            permit()
            if output.write(data) != len(data):
                raise OSError("history write incomplete")
            output.flush()
            os.fsync(output.fileno())
        permit()
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink()
    permit()
    return hashlib.sha256(data).hexdigest()


# Historical inspection is deliberately separate from the live comparison
# engine. No file discovery, database writes, current scope or authorization.
_RECEIPT_FIELDS = {"format", "historical_only", "current_decision",
    "external_authority", "execution_eligible", "rechecked_at",
    "rechecked_comparison_sha256", "comparison", "receipt_sha256"}
_COMPARISON_FIELDS = {"format", "mode", "compared_at", "scope_sha256", "plan_id",
    "equal_declared_timing", "status", "rows", "lowest_declared_total_cents",
    "lowest_declared_cost_ids", "comparison_sha256", *_FLAGS}
_ROW_FIELDS = {"draft_id", "recipient_id", "supplier", "thread_id", "reply_sha256",
    "evidence_reference", "valid_until", "currency", "line_totals_cents",
    "total_cents", "tax_cents", "shipping_cents", "fees_cents", "delivery_days",
    "payment_days", "declaration_sha256"}


def inspect_receipt(data):
    """Validate canonical exported bytes and return minimal historical metadata.

    A self-consistent file can still be fabricated. This does not establish
    authenticity, present validity, supplier identity or execution authority.
    """
    if type(data) is not bytes or not 1 <= len(data) <= MAX_RECEIPT_BYTES:
        raise ValueError("bounded historical receipt bytes required")
    try:
        receipt = json.loads(data.decode("ascii"))
        if (_json(receipt) + "\n").encode("ascii") != data:
            raise ValueError("noncanonical historical receipt")
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise ValueError("invalid historical receipt encoding") from exc
    _shape(receipt, _RECEIPT_FIELDS)
    result = receipt["comparison"]
    _shape(result, _COMPARISON_FIELDS)
    _projection(result)
    scope, plan = _hash(result["scope_sha256"]), _hash(result["plan_id"])
    original = _stored_stamp(result["compared_at"])
    rechecked = _stored_stamp(receipt["rechecked_at"])
    rows = result["rows"]
    if type(rows) is not list or not 2 <= len(rows) <= MAX_QUOTES:
        raise ValueError("invalid historical quotation count")
    parties, references, lengths = set(), set(), set()
    identities = {key: set() for key in ("draft_id", "recipient_id", "thread_id", "reply_sha256")}
    for row in rows:
        _shape(row, _ROW_FIELDS)
        for key, seen in identities.items():
            identity = _hash(row[key])
            if identity in seen:
                raise ValueError("duplicate historical quotation identity")
            seen.add(identity)
        _shape(row["supplier"], {"scheme", "identifier"})
        party = (_scheme(row["supplier"]["scheme"]), _text(row["supplier"]["identifier"], 128))
        reference = row["evidence_reference"]
        parse_reference(reference)
        if party in parties or reference in references:
            raise ValueError("duplicate historical supplier or reply")
        parties.add(party)
        references.add(reference)
        valid = _stored_stamp(row["valid_until"])
        if (valid <= rechecked or valid <= original or
                datetime.fromisoformat(valid) - datetime.fromisoformat(original) > timedelta(days=365)):
            raise ValueError("invalid historical validity")
        lines = row["line_totals_cents"]
        if row["currency"] != "USD" or type(lines) is not list or not 1 <= len(lines) <= MAX_ITEMS:
            raise ValueError("invalid historical quote lines")
        lengths.add(len(lines))
        total = sum(_integer(x, 0, MAX_CENTS) for x in lines)
        total += sum(_integer(row[k], 0, MAX_CENTS) for k in ("tax_cents", "shipping_cents", "fees_cents"))
        if _integer(row["total_cents"], 1, MAX_CENTS) != total:
            raise ValueError("historical total mismatch")
        for key in ("delivery_days", "payment_days"):
            _integer(row[key], 0, 3650)
        payload = {k: v for k, v in row.items() if k != "declaration_sha256"}
        if _digest(_json(payload)) != _hash(row["declaration_sha256"]):
            raise ValueError("historical declaration digest mismatch")
    if len(lengths) != 1:
        raise ValueError("historical RFQ line counts differ")
    equal = len({(r["delivery_days"], r["payment_days"]) for r in rows}) == 1
    ordered = sorted(rows, key=lambda r: (r["total_cents"] if equal else 0, r["declaration_sha256"]))
    minimum = ordered[0]["total_cents"] if equal else None
    ids = [r["declaration_sha256"] for r in ordered if equal and r["total_cents"] == minimum]
    if (result["equal_declared_timing"] is not equal or rows != ordered or
            result["status"] != ("DECLARED_COST_ORDER_ONLY" if equal else "DIFFERENT_TIMING_REVIEW") or
            _json(result["lowest_declared_total_cents"]) != _json(minimum) or
            result["lowest_declared_cost_ids"] != ids):
        raise ValueError("historical ranking mismatch")
    # Reconstruct the only allowable recheck: same projection, new timestamp.
    current = dict(result, compared_at=rechecked)
    current.pop("comparison_sha256")
    current["comparison_sha256"] = _digest(_json(current))
    if _json(historical_receipt(result, current)) != _json(receipt):
        raise ValueError("historical receipt integrity mismatch")
    return dict(receipt_sha256=receipt["receipt_sha256"], scope_sha256=scope,
        plan_id=plan, compared_at=original, rechecked_at=rechecked,
        snapshot_sha256=_digest(_projection(result)),
        quote_count=len(rows), lowest_declared_total_cents=minimum,
        historical_only=True, current_status="NOT_REVALIDATED",
        external_authority=False, execution_eligible=False)


def index_receipts(documents, *, scope_sha256, halted=None):
    """Index an explicit bounded batch by exact scope, never infer supersession.

    Reject the whole batch on malformed input. Exact receipt replay is
    deduplicated; different rechecks remain distinct historical observations.
    This projection has no persistence, filesystem access or current decision.
    """
    decision = decide(Action.EVALUATE, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    scope = _hash(scope_sha256)
    if type(documents) is not list or len(documents) > MAX_INDEX_RECEIPTS:
        raise ValueError("historical index batch exceeds budget")
    matches = {}
    for data in documents:
        item = inspect_receipt(data)
        if item["scope_sha256"] == scope:
            matches[item["receipt_sha256"]] = item
    return annotate_history(list(matches.values()))
