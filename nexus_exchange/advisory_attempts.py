"""Durable reference-only local advisory reservations, not a worker runtime.

One budget per validated saved plan, across model and snapshot changes.
Trusted cooperating caller only; no raw requests, replies, or credentials stored.
"""
from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
from pathlib import Path

from .local_advisory import MAX_ATTEMPTS, _digest, _json, _permit, _pin, _utc, build_request, review_response

MAX_TASKS = 10000
MAX_PAYLOAD = 8192
DB_NAME = "local-advisory.sqlite3"
_FAILURES = ("INVALID_RESPONSE", "TIMEOUT", "WORKER_FAILED")
_TERMINAL = ("REVIEWED", "ESCALATED")
_RECORD = {"version", "plan_id", "attempts"}
_ENTRY = {"attempt", "request_sha256", "snapshot_sha256", "model_sha256", "reserved_at",
          "reservation_id", "state", "reason", "completed_at", "response_sha256", "review_sha256"}
_TICKET = {"plan_id", "attempt", "reservation_id", "request_sha256"}
_FLAGS = ("independently_verified", "execution_eligible", "external_authority", "dispatch_enabled")


def _stamp(value):
    if type(value) is not str:
        raise ValueError("canonical UTC timestamp required")
    stamp = _utc(datetime.fromisoformat(value))
    if stamp.isoformat(timespec="microseconds") != value:
        raise ValueError("noncanonical advisory timestamp")
    return stamp


def _reservation(plan, entry):
    return _digest(dict(plan_id=plan, **{key:entry[key] for key in
        ("attempt", "request_sha256", "snapshot_sha256", "model_sha256", "reserved_at")}))


def _decode(plan, payload, digest):
    if type(payload) is not str or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError("advisory ledger payload bound")
    try:
        record = json.loads(payload)
        if _json(record) != payload or _digest(record) != digest:
            raise ValueError("advisory ledger integrity mismatch")
    except (TypeError, ValueError, RecursionError):
        raise ValueError("invalid advisory ledger encoding") from None
    if (type(record) is not dict or set(record) != _RECORD or type(record["version"]) is not int
            or record["version"] != 1 or _pin(record["plan_id"]) != plan):
        raise ValueError("advisory ledger identity mismatch")
    rows = record["attempts"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ATTEMPTS:
        raise ValueError("advisory attempt count")
    previous = None
    for n, row in enumerate(rows, 1):
        if (type(row) is not dict or set(row) != _ENTRY or type(row["attempt"]) is not int
                or row["attempt"] != n):
            raise ValueError("advisory attempt sequence mismatch")
        for key in ("request_sha256", "snapshot_sha256", "model_sha256", "reservation_id"):
            _pin(row[key])
        if row["reservation_id"] != _reservation(plan, row):
            raise ValueError("advisory reservation identity mismatch")
        reserved = _stamp(row["reserved_at"])
        if previous is not None and reserved < previous:
            raise ValueError("advisory clock moved backward")
        state = row["state"]
        if state == "RESERVED":
            if n != len(rows) or any(row[k] is not None for k in
                    ("reason", "completed_at", "response_sha256", "review_sha256")):
                raise ValueError("invalid open advisory reservation")
            continue
        completed = _stamp(row["completed_at"])
        if completed < reserved:
            raise ValueError("advisory completion predates reservation")
        if state == "REVIEWED":
            if row["reason"] is not None:
                raise ValueError("reviewed attempt has failure reason")
            _pin(row["response_sha256"])
            _pin(row["review_sha256"])
        else:
            reason = row["reason"]
            expected = ("ESCALATED" if n == MAX_ATTEMPTS else
                        "INTERRUPTED" if reason == "INTERRUPTED" else "FAILED")
            if (reason not in (*_FAILURES, "INTERRUPTED") or state != expected
                    or row["response_sha256"] is not None or row["review_sha256"] is not None):
                raise ValueError("invalid advisory failure state")
        if state in _TERMINAL and n != len(rows):
            raise ValueError("attempt after terminal state")
        previous = completed
    return record


def _state(record):
    rows = record["attempts"]
    state = rows[-1]["state"]
    return dict(plan_id=record["plan_id"], state=state, attempts_used=len(rows),
                next_attempt=len(rows)+1 if state not in (*_TERMINAL, "RESERVED") else None,
                attempts=[dict(row) for row in rows], durable_retry_enforced=True,
                historical_only=True, **dict.fromkeys(_FLAGS, False))


class AdvisoryAttemptStore:
    """Bounded SQLite ledger for a trusted coordinator; no inference or dispatch."""
    def __init__(self, path, *, existing_only=False):
        path = Path(path)
        if type(existing_only) is not bool or path.is_symlink():
            raise ValueError("invalid advisory ledger path or mode")
        exists = path.exists()
        if (existing_only and not exists) or (exists and not path.is_file()):
            raise ValueError("existing advisory ledger required")
        self.db = sqlite3.connect(path.resolve().as_uri()+"?mode=rw", uri=True, timeout=5,
                                  isolation_level=None) if exists else sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            if exists and self.db.execute("SELECT type FROM sqlite_master WHERE name=?",
                    ("advisory_attempts_v1",)).fetchone() != ("table",):
                raise ValueError("existing advisory ledger schema missing")
            self.db.execute("""CREATE TABLE IF NOT EXISTS advisory_attempts_v1(
                plan_id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

    @contextmanager
    def _transaction(self, *, write=True):
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _read(self, plan):
        row = self.db.execute("SELECT payload,digest FROM advisory_attempts_v1 WHERE plan_id=?", (_pin(plan),)).fetchone()
        return None if row is None else _decode(plan, *row)

    def _require(self, plan):
        record = self._read(plan)
        if record is None:
            raise ValueError("unknown advisory plan")
        return record

    def _write(self, record, *, new=False):
        plan = record["plan_id"]
        payload, digest = _json(record), _digest(record)
        _decode(plan, payload, digest)
        if new:
            self.db.execute("INSERT INTO advisory_attempts_v1 VALUES (?,?,?)", (plan, payload, digest))
        else:
            self.db.execute("UPDATE advisory_attempts_v1 SET payload=?,digest=? WHERE plan_id=?", (payload, digest, plan))

    @staticmethod
    def _clock(record, now):
        row = record["attempts"][-1]
        if now < _stamp(row["completed_at"] or row["reserved_at"]):
            raise ValueError("advisory clock moved backward")

    def status(self, plan, *, halted=None):
        _permit(True, halted)
        with self._transaction(write=False):
            return _state(self._require(plan))

    def preview_budget(self, plan, *, halted=None):
        """Read only: missing plan is not a reservation or permission."""
        _permit(True, halted)
        with self._transaction(write=False):
            record = self._read(plan)
            if record is None:
                return dict(state="NOT_STARTED", attempts_used=0, next_attempt=1)
            state = _state(record)
            return {key:state[key] for key in ("state", "attempts_used", "next_attempt")}

    def reserve(self, snapshot, model, *, now, approved=None, halted=None):
        _permit(approved, halted)
        now = _utc(now)
        if type(snapshot) is not dict:
            raise ValueError("validated Council snapshot required")
        plan = _pin(snapshot.get("plan_id"))
        with self._transaction():
            record = self._read(plan)
            new = record is None
            if new:
                if self.db.execute("SELECT COUNT(*) FROM advisory_attempts_v1").fetchone()[0] >= MAX_TASKS:
                    raise ValueError("advisory ledger capacity review required")
                record = dict(version=1, plan_id=plan, attempts=[])
            else:
                self._clock(record, now)
                if _state(record)["next_attempt"] is None:
                    raise PermissionError("advisory attempt unavailable")
            n = len(record["attempts"]) + 1
            request = build_request(snapshot, model, n, now=now, approved=approved, halted=halted)
            row = dict(attempt=n, request_sha256=request["request_sha256"], snapshot_sha256=request["snapshot_sha256"],
                       model_sha256=request["model_sha256"], reserved_at=request["created_at"], state="RESERVED",
                       reason=None, completed_at=None, response_sha256=None, review_sha256=None)
            row["reservation_id"] = _reservation(plan, row)
            record["attempts"].append(row)
            self._write(record, new=new)
            return dict(request=request, ticket=dict(plan_id=plan, attempt=n,
                       reservation_id=row["reservation_id"], request_sha256=row["request_sha256"]))

    def _open(self, ticket, now):
        if type(ticket) is not dict or set(ticket) != _TICKET or type(ticket["attempt"]) is not int:
            raise ValueError("invalid advisory ticket")
        record = self._require(ticket["plan_id"])
        self._clock(record, now)
        row = record["attempts"][-1]
        if (row["state"] != "RESERVED" or any(ticket[k] != row[k] for k in
                ("attempt", "reservation_id", "request_sha256"))):
            raise ValueError("stale or mismatched advisory ticket")
        return record, row

    def complete(self, ticket, request, snapshot, raw, *, now, approved=None, halted=None, worker_drained=None):
        """Exact original snapshot review; not a fresh owner inspection."""
        return self._complete(ticket, request, snapshot, raw, now=now, approved=approved,
                              halted=halted, worker_drained=worker_drained)

    def complete_current(self, ticket, request, original, current, raw, *, now,
                         approved=None, halted=None, worker_drained=None):
        """Complete only after independent fresh trusted saved-plan inspection."""
        if type(current) is not dict:
            raise ValueError("fresh advisory snapshot required")
        return self._complete(ticket, request, original, raw, now=now, approved=approved,
                              halted=halted, worker_drained=worker_drained, current=current)

    def _complete(self, ticket, request, snapshot, raw, *, now, approved, halted,
                  worker_drained, current=None):
        _permit(approved, halted)
        if worker_drained is not True:
            raise PermissionError("worker drain required")
        now = _utc(now)
        with self._transaction():
            record, row = self._open(ticket, now)
            if (type(request) is not dict or type(snapshot) is not dict
                    or snapshot.get("plan_id") != record["plan_id"]
                    or type(request.get("attempt")) is not int
                    or any(request.get(k) != row[k] for k in
                           ("attempt", "request_sha256", "snapshot_sha256", "model_sha256"))
                    or request.get("created_at") != row["reserved_at"]):
                raise ValueError("advisory request does not match reservation")
            if current is None:
                review = review_response(raw, request, snapshot, now=now, approved=approved, halted=halted)
            else:
                from .advisory_current_scope import review_current_response
                review = review_current_response(raw, request, snapshot, current, now=now,
                                                 approved=approved, halted=halted)
            row.update(state="REVIEWED", completed_at=now.isoformat(timespec="microseconds"),
                       response_sha256=review["response_sha256"], review_sha256=_digest(review))
            self._write(record)
            return dict(_state(record), review=review)

    def _failure(self, record, row, reason, now):
        row.update(state="ESCALATED" if row["attempt"] == MAX_ATTEMPTS else
                   "INTERRUPTED" if reason == "INTERRUPTED" else "FAILED",
                   reason=reason, completed_at=now.isoformat(timespec="microseconds"))
        self._write(record)
        return _state(record)

    def fail(self, ticket, reason, *, now, approved=None, halted=None, worker_drained=None):
        _permit(approved, halted)
        if worker_drained is not True:
            raise PermissionError("worker drain required")
        if reason not in _FAILURES:
            raise ValueError("fixed advisory failure reason required")
        now = _utc(now)
        with self._transaction():
            record, row = self._open(ticket, now)
            return self._failure(record, row, reason, now)

    def recover_interrupted(self, plan, *, now, halted=None, exclusive_owner=None, worker_drained=None):
        """Halted maintenance; caller must actually hold exclusive ownership and drain workers."""
        if halted is not True or exclusive_owner is not True or worker_drained is not True:
            raise PermissionError("halted exclusive drained recovery required")
        now = _utc(now)
        with self._transaction():
            record = self._require(plan)
            self._clock(record, now)
            row = record["attempts"][-1]
            if row["state"] != "RESERVED":
                return _state(record)
            return self._failure(record, row, "INTERRUPTED", now)

    def _runtime_plan_ids(self):
        rows = self.db.execute("SELECT plan_id FROM advisory_attempts_v1 ORDER BY plan_id LIMIT ?",
                               (MAX_TASKS + 1,)).fetchall()
        if len(rows) > MAX_TASKS:
            raise ValueError("advisory runtime recovery capacity exceeded")
        return tuple(_pin(row[0]) for row in rows)

    def _runtime_pending(self, *, now):
        """Private maintenance read; caller must hold the runtime directory lock."""
        now = _utc(now)
        with self._transaction(write=False):
            pending = 0
            for plan in self._runtime_plan_ids():
                record = self._require(plan)
                self._clock(record, now)
                pending += _state(record)["state"] == "RESERVED"
            return pending

    def _runtime_recover_all(self, *, now):
        """Private halted reconciliation, only under exclusive drained ownership.

        Validate all bounded records and commit all transitions or none. Never
        resume or dispatch a model. Future workers require actual child cleanup.
        """
        now = _utc(now)
        recovered = escalated = 0
        with self._transaction():
            for plan in self._runtime_plan_ids():
                record = self._require(plan)
                self._clock(record, now)
                row = record["attempts"][-1]
                if row["state"] != "RESERVED":
                    continue
                self._failure(record, row, "INTERRUPTED", now)
                recovered += 1
                escalated += row["state"] == "ESCALATED"
        return dict(recovered=recovered, escalated=escalated)
