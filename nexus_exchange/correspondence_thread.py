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


# Persistent local compare-and-append. The single-user runtime supplies the
# exact saved draft and recipient; hashes are not authentication.
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

MAX_THREADS = 1000
MAX_THREAD_PAYLOAD = 32768
_TABLE = "operator_threads_v1"
_THREAD_READ_COLUMNS = ", ".join(
    f"CASE WHEN typeof({column})='text' AND length(CAST({column} AS BLOB))<={limit} THEN {column} END"
    for column, limit in (("draft_id",64),("recipient_id",64),("thread_id",64),
                          ("head_sha256",64),("payload","?"),("digest",64)))


class ThreadStore:
    """One non-resettable history per exact draft/recipient pair.

    Uses a separate bounded local SQLite database. No message contents, file
    paths, addresses or external authority are stored here.
    """

    def __init__(self, path, *, existing_only=False):
        if type(existing_only) is not bool:
            raise ValueError("invalid thread storage mode")
        path = Path(path)
        exists = os.path.lexists(path)
        if exists and (path.is_symlink() or not path.is_file()):
            raise ValueError("invalid thread database path")
        if existing_only and not exists:
            raise ValueError("existing thread database required")
        self.db = sqlite3.connect(path.resolve().as_uri() + ("?mode=rw" if existing_only else "?mode=rwc"),
                                  uri=True, timeout=5, isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            if existing_only:
                if self.db.execute("SELECT type FROM sqlite_master WHERE name=?", (_TABLE,)).fetchone() != ("table",):
                    raise ValueError("thread storage schema missing")
            else:
                self.db.execute("""CREATE TABLE IF NOT EXISTS operator_threads_v1(
                    draft_id TEXT NOT NULL, recipient_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL UNIQUE, head_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL, digest TEXT NOT NULL,
                    PRIMARY KEY(draft_id,recipient_id))""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def _scope(draft, recipient):
        candidate = _for_draft(draft, recipient)
        return draft["draft_id"], candidate["recipient_id"]

    @staticmethod
    def _row(thread):
        payload = _json(thread)
        if len(payload) > MAX_THREAD_PAYLOAD:
            raise ValueError("thread storage payload exceeds bound")
        return (thread["draft_id"], thread["recipient_id"], thread["thread_id"],
                thread["head_sha256"], payload, _digest(payload))

    def _read(self, draft, recipient):
        scope = self._scope(draft, recipient)
        # Bound every projected column by bytes before materializing in Python.
        row = self.db.execute("SELECT "+_THREAD_READ_COLUMNS+"""
            FROM operator_threads_v1 WHERE draft_id=? AND recipient_id=?""",
            (MAX_THREAD_PAYLOAD, *scope)).fetchone()
        if row is None:
            return None
        payload = row[4]
        if (any(type(value) is not str for value in row) or not payload.isascii()
                or _digest(payload) != row[5]):
            raise ValueError("thread storage integrity mismatch")
        try:
            checked = validate_thread(draft, recipient, json.loads(payload), halted=False)
        except (ValueError, RecursionError, TypeError) as exc:
            raise ValueError("thread storage validation failed") from None
        if self._row(checked) != row:
            raise ValueError("stored thread identity mismatch")
        return checked

    def get(self, draft, recipient, *, halted=None):
        _permit(halted)
        return self._read(draft, recipient)

    def open(self, draft, recipient, *, now, confirmed=None, halted=None):
        proposed = open_thread(draft, recipient, now=now, confirmed=confirmed, halted=halted)
        with self._transaction():
            current = self._read(draft, recipient)
            if current is not None:
                last = current["events"][-1]["recorded_at"] if current["events"] else current["created_at"]
                if proposed["created_at"] < last:
                    raise ValueError("thread replay clock moved backward")
                return current
            if self.db.execute("SELECT COUNT(*) FROM operator_threads_v1").fetchone()[0] >= MAX_THREADS:
                raise ValueError("thread storage capacity review required")
            self.db.execute("INSERT INTO operator_threads_v1 VALUES (?,?,?,?,?,?)", self._row(proposed))
            return proposed

    def append(self, draft, recipient, *, kind, evidence_reference, now,
               expected_head, confirmed=None, halted=None):
        _permit(halted)
        if confirmed is not True:
            raise PermissionError("explicit local event confirmation required")
        _hash(expected_head)
        with self._transaction():
            current = self._read(draft, recipient)
            if current is None:
                raise ValueError("saved correspondence thread required")
            updated = append_event(draft, recipient, current, kind=kind,
                evidence_reference=evidence_reference, now=now, expected_head=expected_head,
                confirmed=True, halted=False)
            row = self._row(updated)
            changed = self.db.execute("""UPDATE operator_threads_v1
                SET head_sha256=?,payload=?,digest=?
                WHERE draft_id=? AND recipient_id=? AND thread_id=? AND head_sha256=?""",
                (row[3], row[4], row[5], row[0], row[1], row[2], expected_head))
            if changed.rowcount != 1:
                raise ValueError("thread head changed; inspect again")
            return updated
