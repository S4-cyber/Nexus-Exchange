"""H08/E25: bounded local correspondence thread model; no delivery or reply authentication."""
from datetime import datetime

from .evidence import parse_reference
from .operator_drafts import _digest, _hash, _json, _permit, _shape, _stamp, _stored_stamp
from .operator_recipients import _for_draft, _fresh, _FLAGS_EXTRA

FORMAT = "nexus-correspondence-thread-v1"
MAX_EVENTS = 32
_FLAGS = (*_FLAGS_EXTRA, "delivery_verified", "reply_authenticated", "commitment_enabled")
_KINDS = frozenset(("SIMULATED_REPLY", "LOCAL_EVIDENCE_DECLARATION", "LOCAL_FOLLOWUP_DRAFT"))
_FIELDS = {"format", "thread_id", "draft_id", "recipient_id", "created_at",
           "events", "head_sha256", *_FLAGS}


def _flags():
    return dict.fromkeys(_FLAGS, False)


def _identity(draft, recipient, stamp):
    return dict(format=FORMAT, draft_id=draft["draft_id"],
                recipient_id=recipient["recipient_id"], created_at=stamp)


def _event(thread_id, parent, sequence, kind, evidence_reference, stamp):
    if type(kind) is not str or kind not in _KINDS:
        raise ValueError("unknown or external correspondence event")
    parse_reference(evidence_reference)
    payload = dict(thread_id=thread_id, parent_sha256=parent, sequence=sequence,
                   kind=kind, evidence_reference=evidence_reference, recorded_at=stamp)
    return dict(payload, event_sha256=_digest(_json(payload)))


def open_thread(draft, recipient, *, now, confirmed=None, halted=None):
    """Create an empty local history, not a sent-message record."""
    _permit(halted)
    if confirmed is not True:
        raise PermissionError("explicit local thread confirmation required")
    candidate = _for_draft(draft, recipient)
    _fresh(candidate["recipient"], now)
    identity = _identity(draft, candidate, _stamp(now))
    key = _digest(_json(identity))
    return dict(identity, thread_id=key, head_sha256=key, events=[], **_flags())


def validate_thread(draft, recipient, thread, *, halted=None):
    """Rebuild the entire bounded chain; digest consistency is not authentication."""
    _permit(halted)
    candidate = _for_draft(draft, recipient)
    _shape(thread, _FIELDS)
    stamp = _stored_stamp(thread["created_at"])
    _fresh(candidate["recipient"], datetime.fromisoformat(stamp))
    identity = _identity(draft, candidate, stamp)
    key = _digest(_json(identity))
    events = thread["events"]
    if type(events) is not list or len(events) > MAX_EVENTS:
        raise ValueError("correspondence history capacity exceeded")
    parent = key
    previous = stamp
    rebuilt = []
    references = set()
    for index, raw in enumerate(events, 1):
        _shape(raw, {"thread_id", "parent_sha256", "sequence", "kind",
                     "evidence_reference", "recorded_at", "event_sha256"})
        event_stamp = _stored_stamp(raw["recorded_at"])
        if event_stamp < previous:
            raise ValueError("correspondence clock moved backward")
        event = _event(key, parent, index, raw["kind"], raw["evidence_reference"], event_stamp)
        if type(raw["sequence"]) is not int or event != raw:
            raise ValueError("correspondence event integrity mismatch")
        reference = event["evidence_reference"]
        if reference in references:
            raise ValueError("duplicate evidence in correspondence thread")
        references.add(reference)
        rebuilt.append(event)
        parent, previous = event["event_sha256"], event_stamp
    expected = dict(identity, thread_id=key, head_sha256=parent, events=rebuilt, **_flags())
    if any(thread[k] is not False for k in _FLAGS) or thread != expected:
        raise ValueError("correspondence scope, integrity or authority mismatch")
    return expected


def append_event(draft, recipient, thread, *, kind, evidence_reference, now,
                 expected_head, confirmed=None, halted=None):
    """Return a new immutable-by-convention snapshot after explicit local confirmation.

    This is an in-memory compare-and-append contract, not a durable CAS or outbox.
    No raw message, address, attachment bytes or evidence path is accepted.
    """
    _permit(halted)
    if confirmed is not True:
        raise PermissionError("explicit local event confirmation required")
    current = validate_thread(draft, recipient, thread, halted=False)
    if _hash(expected_head) != current["head_sha256"]:
        raise ValueError("correspondence head changed; inspect again")
    if len(current["events"]) >= MAX_EVENTS:
        raise ValueError("correspondence history capacity exceeded")
    stamp = _stamp(now)
    event = _event(current["thread_id"], current["head_sha256"],
                   len(current["events"]) + 1, kind, evidence_reference, stamp)
    proposed = dict(current, events=current["events"] + [event],
                    head_sha256=event["event_sha256"])
    return validate_thread(draft, recipient, proposed, halted=False)
