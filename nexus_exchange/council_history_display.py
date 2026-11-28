"""Fixed, reference-only display for a trusted local Council history result.

This is a consistency check, not authentication of a runtime or a fresh
commercial decision. Never render arbitrary packet or supplier text.
"""
from datetime import datetime

from .context_packet import FALSE_FLAGS
from .local_advisory import MAX_REQUEST_BYTES, _digest, _json
from .operator_drafts import _hash, _stored_stamp
from .quote_comparison import compare_quotes
from .quote_history_recall import build_recall

_OUTER_FLAGS = ("history_used_for_scoring", "current_decision",
                "independently_verified", "external_authority",
                "dispatch_enabled", "execution_eligible", "release_eligible")
_HISTORY_FLAGS = ("current_decision", "independently_verified",
                  "external_authority", "execution_eligible")


def _checked(value, digest_key, flags):
    if (type(value) is not dict or any(value.get(key) is not False for key in flags)
            or _hash(value.get(digest_key)) != _digest(
                {key: item for key, item in value.items() if key != digest_key})):
        raise ValueError("history context integrity or authority mismatch")


def render_history_context(context, plan, staged, retained):
    """Reproduce the visible scope/recall from trusted local inputs.

    The separate post-read may detect changed history; it is not a distributed
    transaction. A rehashed Council packet is not independently authenticated.
    Only validated fixed identifiers, timestamps and counts are displayed.
    """
    try:
        if type(context) is not dict or len(_json(context).encode("ascii")) > MAX_REQUEST_BYTES:
            raise ValueError("bounded Council history context required")
        _checked(context, "context_sha256", _OUTER_FLAGS)
        if context.get("format") != "nexus-council-history-context-v1" or context.get("plan_id") != _hash(plan):
            raise ValueError("Council history outside saved plan")
        packet, history = context["council"], context["history"]
        _checked(packet, "packet_sha256", FALSE_FLAGS)
        _checked(history, "context_sha256", _HISTORY_FLAGS)
        if (packet.get("format") != "nexus-council-context-v1" or packet.get("level") != "evidence"
                or packet.get("plan_id") != plan
                or history.get("format") != "nexus-reviewed-history-context-v1"
                or history.get("historical_only") is not True):
            raise ValueError("Council history scope mismatch")
        snapshot = _hash(packet["snapshot_sha256"])
        _hash(context["original_snapshot_sha256"])
        _hash(context["current_scope_sha256"])
        _hash(history["reviewed_comparison_sha256"])
        stamp = datetime.fromisoformat(_stored_stamp(history["rechecked_at"]))
        evaluated = datetime.fromisoformat(_stored_stamp(packet["evaluated_at"]))
        if stamp > evaluated:
            raise ValueError("RFQ review postdates Council inspection")
        comparison = compare_quotes(staged, now=stamp, halted=False)
        if (comparison["plan_id"] != plan or
                comparison["comparison_sha256"] != history["rechecked_comparison_sha256"]):
            raise ValueError("Council history differs from staged RFQ")
        scope = comparison["scope_sha256"]
        for row in staged:
            request = row["draft"]["request"]
            if any(packet["scope"][key] != request[key] for key in
                   ("observation_sha256", "profile_revision")):
                raise ValueError("Council and RFQ evidence scope mismatch")
        expected = build_recall(retained, plan, scope, limit=8)
        if _json(history["recall"]) != _json(expected):
            raise ValueError("retained historical references changed")
        if any(datetime.fromisoformat(row["rechecked_at"]) > stamp
               for row in expected["references"]):
            raise ValueError("historical observation postdates RFQ review")
        lines = [
            "COUNCIL HISTORY — UNVERIFIED LOCAL REFERENCES ONLY",
            "No current decision, score change, worker attempt or commercial authority.",
            "Saved plan: " + plan,
            "Council snapshot: " + snapshot,
            "Council evaluated UTC: " + packet["evaluated_at"],
            "RFQ scope: " + scope,
            "RFQ rechecked UTC: " + history["rechecked_at"],
            "Context fingerprint: " + context["context_sha256"],
            "Historical matching receipts: " + str(expected["matching_receipts"]),
            "Distinct historical snapshots: " + str(expected["distinct_snapshots"]),
            "References shown: " + str(len(expected["references"])) +
                (" (truncated)" if expected["truncated"] else ""),
            "Historical validity: not revalidated; supersession not established.",
        ]
        for row in expected["references"]:
            lines.extend(["", "Receipt: " + row["receipt_sha256"],
                          "Snapshot: " + row["snapshot_sha256"],
                          "Rechecked UTC: " + row["rechecked_at"],
                          "Retained observations: " + str(row["observations"])])
        return "\n".join(lines)
    except (KeyError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid Council history display projection") from exc
