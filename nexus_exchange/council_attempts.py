"""Bounded, durable local Council attempt ledger; never execution authority.

Trusted coordinator code alone may allocate task IDs, reserve attempts,
record a review result digest or establish exclusive recovery ownership.
A reservation or completion is not an authenticated reviewer verdict.
"""
from contextlib import contextmanager
from dataclasses import fields
import json
import re
import sqlite3

from .agent_handoff import AgentHandoff, MAX_ATTEMPTS, parse_handoff
from .council_audit import MAX_AUDIT_BYTES, build_audit, validate_audit
from .governor import Action, decide
from .lead_store import _digest, _json, _now
from .schedule_feasibility import _iso
from .scout import _timestamp

MAX_TASKS=10000
MAX_PAYLOAD=8192
_TASK=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHA=re.compile(r"[0-9a-f]{64}")
_REVIEW={"RETRY","NEEDS_EVIDENCE","ADVANCE_REVIEW_ONLY","ESCALATE"}
_TERMINAL={"ADVANCE_REVIEW_ONLY","ESCALATE"}
_RECORD={"version","task_id","contract_sha256","created_at","attempts"}
_ENTRY={"attempt","reservation_id","reserved_at","outcome","completed_at","report_sha256"}
_TICKET={"task_id","attempt","reservation_id"}


def _permit(halted):
    if not decide(Action.EVALUATE,halted=halted).allowed:
        raise PermissionError("HALTED_OR_UNKNOWN")


def _task(value):
    if type(value) is not str or _TASK.fullmatch(value) is None:
        raise ValueError("invalid task ID")
    return value


def _hash(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 digest")
    return value


def _contract(handoff):
    if type(handoff) is not AgentHandoff:
        raise ValueError("normalized handoff required")
    h=parse_handoff({field.name:getattr(handoff,field.name) for field in fields(AgentHandoff)})
    raw={field.name:getattr(h,field.name) for field in fields(AgentHandoff)
         if field.name!="attempt"}
    return h,_digest(_json(raw))


def _reservation(record,attempt,stamp):
    return _digest(_json(dict(task_id=record["task_id"],
        contract_sha256=record["contract_sha256"],attempt=attempt,reserved_at=stamp)))


def _stamp(value):
    if type(value) is not str:
        raise ValueError("canonical UTC stamp required")
    parsed=_timestamp(value)
    if _iso(parsed)!=value:
        raise ValueError("noncanonical UTC stamp")
    return parsed


def _decode(task_id,encoded,digest):
    if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
        raise ValueError("Council journal integrity mismatch")
    record=json.loads(encoded)
    if (type(record) is not dict or set(record)!=_RECORD
            or type(record["version"]) is not int or record["version"] not in (1,2)
            or _task(record["task_id"])!=task_id):
        raise ValueError("invalid Council task record")
    _hash(record["contract_sha256"])
    previous=_stamp(record["created_at"])
    entries=record["attempts"]
    if type(entries) is not list or len(entries)>MAX_ATTEMPTS:
        raise ValueError("invalid Council attempt history")
    entry_fields=_ENTRY if record["version"]==1 else _ENTRY|{"audit_sha256"}
    for n,entry in enumerate(entries,1):
        if (type(entry) is not dict or set(entry)!=entry_fields
                or type(entry["attempt"]) is not int or entry["attempt"]!=n
                or _hash(entry["reservation_id"])!=_reservation(record,n,entry["reserved_at"])):
            raise ValueError("invalid Council reservation identity")
        reserved=_stamp(entry["reserved_at"])
        if reserved<previous:
            raise ValueError("Council clock moved backward")
        outcome=entry["outcome"]
        audit=entry.get("audit_sha256")
        if audit is not None:
            _hash(audit)
            if outcome is None or entry["report_sha256"] is None:
                raise ValueError("audit requires completed review")
        if outcome is None:
            if n!=len(entries) or entry["completed_at"] is not None or entry["report_sha256"] is not None:
                raise ValueError("invalid outstanding Council attempt")
            continue
        if type(outcome) is not str or outcome not in _REVIEW|{"INTERRUPTED"}:
            raise ValueError("invalid Council outcome")
        completed=_stamp(entry["completed_at"])
        if completed<reserved:
            raise ValueError("Council completion predates reservation")
        report=entry["report_sha256"]
        if outcome=="INTERRUPTED":
            if n==MAX_ATTEMPTS or report is not None:
                raise ValueError("invalid interrupted attempt")
        elif report is None:
            if outcome!="ESCALATE" or n!=MAX_ATTEMPTS:
                raise ValueError("review report digest required")
        else:
            _hash(report)
        if n==MAX_ATTEMPTS and outcome not in _TERMINAL:
            raise ValueError("third attempt must be terminal")
        if outcome in _TERMINAL and n!=len(entries):
            raise ValueError("attempt after terminal outcome")
        previous=completed
    if _json(record)!=encoded:
        raise ValueError("noncanonical Council task record")
    return record


def _state(record):
    entries=record["attempts"]
    if not entries:
        state="READY"
    else:
        state=entries[-1]["outcome"] or "RESERVED"
    next_attempt=(len(entries)+1 if state not in _TERMINAL|{"RESERVED"}
                  and len(entries)<MAX_ATTEMPTS else None)
    return dict(task_id=record["task_id"],contract_sha256=record["contract_sha256"],
                state=state,attempts_used=len(entries),next_attempt=next_attempt,
                attempts=[dict(entry) for entry in entries],durable_retry_enforced=True,
                independently_verified=False,commercial_facts_verified=False,
                independent_reviewer_authenticated=False,execution_eligible=False,
                release_eligible=False,external_authority=False)


class CouncilAttemptStore:
    """Single-user local ledger; trusted coordinator boundary, no background jobs."""
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("""CREATE TABLE IF NOT EXISTS council_attempts_v1(
                task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,digest TEXT NOT NULL)""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS council_review_audit_v1(
                task_id TEXT NOT NULL,attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 3),
                payload TEXT NOT NULL,digest TEXT NOT NULL,
                PRIMARY KEY(task_id,attempt),FOREIGN KEY(task_id) REFERENCES council_attempts_v1(task_id))""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    @contextmanager
    def _transaction(self,halted,*,write=True):
        _permit(halted)
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _read(self,task_id):
        row=self.db.execute("SELECT payload,digest FROM council_attempts_v1 WHERE task_id=?",
                            (_task(task_id),)).fetchone()
        if row is None:
            return None
        record=_decode(task_id,*row)
        self._read_audits(record)
        return record

    def _read_audits(self,record):
        expected={entry["attempt"]:entry for entry in record["attempts"]
                  if entry.get("audit_sha256") is not None}
        rows=self.db.execute("""SELECT attempt,payload,digest FROM council_review_audit_v1
            WHERE task_id=? ORDER BY attempt LIMIT ?""",(record["task_id"],MAX_ATTEMPTS+1)).fetchall()
        if len(rows)!=len(expected):
            raise ValueError("missing or orphaned Council audit")
        result={}
        for attempt,payload,digest in rows:
            if (type(attempt) is not int or attempt not in expected or attempt in result
                    or type(payload) is not str or len(payload)>MAX_AUDIT_BYTES
                    or digest!=expected[attempt]["audit_sha256"] or _digest(payload)!=digest):
                raise ValueError("Council audit integrity mismatch")
            audit=json.loads(payload)
            if _json(audit)!=payload:
                raise ValueError("noncanonical Council audit record")
            result[attempt]=validate_audit(audit,record,expected[attempt])
        return result

    def _require(self,task_id):
        record=self._read(task_id)
        if record is None:
            raise ValueError("Council task not registered")
        return record

    def _write(self,record,*,new=False):
        payload=_json(record)
        digest=_digest(payload)
        _decode(record["task_id"],payload,digest)
        if new:
            self.db.execute("INSERT INTO council_attempts_v1 VALUES (?,?,?)",
                            (record["task_id"],payload,digest))
        else:
            self.db.execute("UPDATE council_attempts_v1 SET payload=?,digest=? WHERE task_id=?",
                            (payload,digest,record["task_id"]))

    @staticmethod
    def _clock(record,now):
        latest=record["created_at"]
        if record["attempts"]:
            entry=record["attempts"][-1]
            latest=entry["completed_at"] or entry["reserved_at"]
        if now<_stamp(latest):
            raise ValueError("Council clock moved backward")

    def status(self,task_id,*,halted=None):
        with self._transaction(halted,write=False):
            return _state(self._require(task_id))

    def audit_history(self,task_id,*,halted=None):
        """Historical records only; never revalidate a current commercial decision."""
        with self._transaction(halted,write=False):
            record=self._require(task_id)
            audits=self._read_audits(record)
            result=_state(record)
            attempts=[]
            for entry in record["attempts"]:
                audit=audits.get(entry["attempt"])
                label=("RECORDED" if audit is not None else
                       "RESERVED_NO_REPORT" if entry["outcome"] is None else
                       "INTERRUPTED_NO_REPORT" if entry["report_sha256"] is None else
                       "LEGACY_DIGEST_ONLY")
                attempts.append(dict(entry,audit_sha256=entry.get("audit_sha256"),
                                     audit_state=label,audit=audit))
            return dict(result,format="nexus-council-audit-history-v1",
                        attempts=attempts,historical_only=True,current_decision=False)

    def register(self,handoff,*,now,halted=None):
        _permit(halted)
        now=_now(now)
        h,digest=_contract(handoff)
        if h.attempt!=1:
            raise ValueError("registration requires first attempt")
        with self._transaction(halted):
            record=self._read(h.task_id)
            if record is not None:
                if record["contract_sha256"]!=digest:
                    raise ValueError("immutable Council task changed")
                self._clock(record,now)
                return _state(record)
            if self.db.execute("SELECT COUNT(*) FROM council_attempts_v1").fetchone()[0]>=MAX_TASKS:
                raise ValueError("Council task capacity review required")
            record=dict(version=1,task_id=h.task_id,contract_sha256=digest,
                        created_at=_iso(now),attempts=[])
            self._write(record,new=True)
            return _state(record)

    def reserve(self,handoff,*,now,halted=None):
        _permit(halted)
        now=_now(now)
        h,digest=_contract(handoff)
        with self._transaction(halted):
            record=self._require(h.task_id)
            if record["contract_sha256"]!=digest:
                raise ValueError("immutable Council task changed")
            self._clock(record,now)
            if _state(record)["next_attempt"]!=h.attempt:
                raise PermissionError("attempt unavailable or out of sequence")
            stamp=_iso(now)
            token=_reservation(record,h.attempt,stamp)
            entry=dict(attempt=h.attempt,reservation_id=token,
                reserved_at=stamp,outcome=None,completed_at=None,report_sha256=None)
            if record["version"]==2:
                entry["audit_sha256"]=None
            record["attempts"].append(entry)
            self._write(record)
        return dict(task_id=h.task_id,attempt=h.attempt,reservation_id=token)

    def complete(self,ticket,outcome,report_sha256,*,now,halted=None,
                 audit_snapshot=None,review_report=None):
        """Complete and optionally atomically retain a validated scenario review audit."""
        _permit(halted)
        now=_now(now)
        if type(ticket) is not dict or set(ticket)!=_TICKET:
            raise ValueError("invalid Council reservation")
        task=_task(ticket["task_id"])
        attempt=ticket["attempt"]
        token=_hash(ticket["reservation_id"])
        if (type(attempt) is not int or not 1<=attempt<=MAX_ATTEMPTS
                or type(outcome) is not str or outcome not in _REVIEW):
            raise ValueError("invalid Council completion")
        _hash(report_sha256)
        if (audit_snapshot is None)!=(review_report is None):
            raise ValueError("complete Council audit material required")
        audited=audit_snapshot is not None
        if attempt==MAX_ATTEMPTS and outcome not in _TERMINAL:
            outcome="ESCALATE"
        with self._transaction(halted):
            record=self._require(task)
            self._clock(record,now)
            entries=record["attempts"]
            if len(entries)!=attempt or entries[-1]["reservation_id"]!=token:
                raise ValueError("stale or mismatched Council reservation")
            entry=entries[-1]
            if entry["outcome"] is not None:
                if (entry["outcome"]!=outcome or entry["report_sha256"]!=report_sha256
                        or audited!=(entry.get("audit_sha256") is not None)):
                    raise ValueError("conflicting Council completion")
                if audited:
                    audit=build_audit(record,entry,audit_snapshot,review_report)
                    if _digest(_json(audit))!=entry["audit_sha256"]:
                        raise ValueError("conflicting historical audit replay")
                return _state(record)
            if record["version"]==2 and not audited:
                raise ValueError("audited Council task cannot downgrade completion")
            entry.update(outcome=outcome,completed_at=_iso(now),report_sha256=report_sha256)
            if audited:
                audit=build_audit(record,entry,audit_snapshot,review_report)
                payload=_json(audit)
                digest=_digest(payload)
                if record["version"]==1:
                    record["version"]=2
                    for prior in entries:
                        prior["audit_sha256"]=None
                entry["audit_sha256"]=digest
                self.db.execute("INSERT INTO council_review_audit_v1 VALUES (?,?,?,?)",
                                (task,attempt,payload,digest))
            self._write(record)
            return _state(record)

    def recover_interrupted(self,task_id,*,now,exclusive_owner=None,halted=None):
        """Only trusted code after exclusive ownership and worker drain may call."""
        _permit(halted)
        if exclusive_owner is not True:
            raise PermissionError("exclusive recovery ownership required")
        now=_now(now)
        with self._transaction(halted):
            record=self._require(task_id)
            self._clock(record,now)
            if _state(record)["state"]!="RESERVED":
                return _state(record)
            entry=record["attempts"][-1]
            entry.update(outcome="ESCALATE" if entry["attempt"]==MAX_ATTEMPTS else "INTERRUPTED",
                         completed_at=_iso(now),report_sha256=None)
            self._write(record)
            return _state(record)
