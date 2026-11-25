"""Durable local CSV obligations and unverified evidence notes.

The ledger records exact local requirements, mechanical QA and selected-file
byte identity. It does not represent a signed contract or customer acceptance.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from .checklist_store import _hash
from .digital_deliverable import _contract, _FLAGS, REPORT, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, _permit, _checks, _output_spec, RECONCILE_FORMAT, RECONCILE_REPORT
from .deliverable_files import preview_pins
from .evidence import parse_reference
from .lead_store import _digest, _json, _now
from .scout import _timestamp
from .scoped_provenance import validate_provenance

FORMAT="nexus-local-csv-obligation-v1"
NOTE_KINDS=("acceptance_claim_noted","revision_request_noted","rejection_claim_noted")
MAX_OBLIGATIONS=10000
MAX_NOTES=16
MAX_PAYLOAD=32768
_FLAGS_EXTRA=tuple(dict.fromkeys((*_FLAGS,"customer_identity_verified",
                                 "evidence_authenticity_verified","payment_received")))


def _stamp(now):
    return _now(now).isoformat(timespec="microseconds")


def _stored_stamp(value):
    if type(value) is not str or _stamp(_timestamp(value))!=value:
        raise ValueError("noncanonical obligation timestamp")
    return value


def _integer(value,maximum):
    return type(value) is int and 1<=value<=maximum


def _shape(value,keys):
    if type(value) is not dict or set(value)!=set(keys):
        raise ValueError("invalid exact obligation schema")


def _qa(contract,report):
    """Reconstruct all report fields from exact contract and bounded identities."""
    spec=contract["specification"]
    if type(report) is not dict:
        raise ValueError("invalid QA metadata")
    reconcile=contract["format"]==RECONCILE_FORMAT
    output_spec=_output_spec(contract,report.get("rows"))
    if not _integer(report.get("input_bytes"),MAX_INPUT_BYTES) or not _integer(report.get("artifact_bytes"),MAX_OUTPUT_BYTES):
        raise ValueError("invalid QA byte count")
    expected=dict(format=RECONCILE_REPORT if reconcile else REPORT,contract_sha256=contract["contract_sha256"],
        plan_id=contract["plan_id"],input_sha256=spec["input_sha256"],
        artifact_sha256=_hash(report.get("artifact_sha256")),input_bytes=report["input_bytes"],
        artifact_bytes=report["artifact_bytes"],rows=output_spec["expected_rows"],
        columns=list(output_spec["columns"]),key_column=output_spec["key_column"],checks=_checks(contract),
        local_criteria_passed=True,**dict.fromkeys(_FLAGS,False))
    if reconcile:
        if not _integer(report.get("right_input_bytes"),MAX_INPUT_BYTES):
            raise ValueError("invalid second input byte count")
        expected.update(right_input_sha256=spec["right_input_sha256"],right_input_bytes=report["right_input_bytes"])
    expected["report_sha256"]=_digest(_json(expected))
    if _json(expected)!=_json(report):
        raise ValueError("QA metadata integrity mismatch")
    return expected


def artifact_reference(result):
    preview_pins(result)
    contract=_contract(result["contract"])
    report=_qa(contract,result["report"])
    if len(result["artifact"])!=report["artifact_bytes"]:
        raise ValueError("artifact size mismatch")
    return "sha256:"+report["artifact_sha256"]+";bytes:"+str(report["artifact_bytes"])


def _binding(contract,report,reference):
    contract=_contract(contract)
    report=_qa(contract,report)
    if parse_reference(reference)!=(report["artifact_sha256"],report["artifact_bytes"]):
        raise ValueError("artifact fingerprint mismatch")
    return dict(format=FORMAT,contract=contract,qa_report=report,artifact_reference=reference,
                **dict.fromkeys(_FLAGS_EXTRA,False))


def _head(payload):
    return _digest(_json(payload))


def _decode(raw,digest):
    if type(raw) is not str or len(raw)>MAX_PAYLOAD or _digest(raw)!=digest:
        raise ValueError("obligation storage integrity mismatch")
    value=json.loads(raw)
    if _json(value)!=raw:
        raise ValueError("noncanonical obligation payload")
    return value


def _record(row,now):
    key,plan,created,encoded,digest=row
    data=_decode(encoded,digest)
    _shape(data,{"binding","created_at","scout_review"} if "scout_review" in data else {"binding","created_at"})
    binding=data["binding"]
    if type(binding) is not dict:
        raise ValueError("invalid obligation binding")
    canonical=_binding(binding.get("contract"),binding.get("qa_report"),binding.get("artifact_reference"))
    stamp=_stored_stamp(data["created_at"])
    if (_json(canonical)!=_json(binding) or key!=_head(canonical)
            or plan!=canonical["contract"]["plan_id"] or stamp!=created
            or _timestamp(stamp)<_timestamp(canonical["contract"]["context"]["retrieved_at"])
            or _timestamp(stamp)>now):
        raise ValueError("obligation identity or timestamp mismatch")
    record=dict(obligation_id=key,plan_id=plan,created_at=stamp,binding=canonical,
                registration_sha256=digest)
    if "scout_review" in data:
        record["scout_review"]=validate_provenance(data["scout_review"],canonical["contract"],
                                                    canonical["qa_report"],stamp)
    return record


def _note(row,record,previous,sequence,seen,now):
    seq,encoded,digest=row
    event=_decode(encoded,digest)
    _shape(event,{"obligation_id","sequence","previous_sha256","kind","reference","recorded_at"})
    kind=event["kind"]
    reference=event["reference"]
    parse_reference(reference)
    stamp=_stored_stamp(event["recorded_at"])
    if (type(seq) is not int or seq!=sequence or type(event["sequence"]) is not int
            or event["sequence"]!=sequence or event["obligation_id"]!=record["obligation_id"]
            or event["previous_sha256"]!=previous or type(kind) is not str or kind not in NOTE_KINDS
            or reference in seen or _timestamp(stamp)>now):
        raise ValueError("obligation note chain mismatch")
    return dict(event,event_sha256=digest)


class ObligationStore:
    """Bounded local append-only note rows; hashes are not digital signatures."""
    def __init__(self,path,*,existing_only=False):
        if path!=":memory:":
            path=Path(path)
            if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
                raise ValueError("invalid obligation database path")
            if existing_only and not path.is_file():
                raise ValueError("obligation database missing")
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            if existing_only:
                names={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"csv_obligations_v1","csv_obligation_notes_v1"}<=names:
                    raise ValueError("obligation schema missing")
            else:
                self.db.execute("""CREATE TABLE IF NOT EXISTS csv_obligations_v1(
                    obligation_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,digest TEXT NOT NULL)""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS csv_obligation_notes_v1(
                    obligation_id TEXT NOT NULL,sequence INTEGER NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,
                    PRIMARY KEY(obligation_id,sequence),
                    FOREIGN KEY(obligation_id) REFERENCES csv_obligations_v1(obligation_id))""")
                self.db.execute("""CREATE INDEX IF NOT EXISTS csv_obligations_plan_v1
                    ON csv_obligations_v1(plan_id,created_at DESC,obligation_id)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    @contextmanager
    def _transaction(self,*,write,halted,halt_check):
        _permit(halted,halt_check)
        self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            _permit(halted,halt_check)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _read(self,plan_id,key,now):
        _hash(plan_id)
        _hash(key)
        row=self.db.execute("""SELECT obligation_id,plan_id,created_at,payload,digest
            FROM csv_obligations_v1 WHERE obligation_id=?""",(key,)).fetchone()
        if row is None or row[1]!=plan_id:
            raise ValueError("obligation outside selected plan or unavailable")
        record=_record(row,now)
        rows=self.db.execute("""SELECT sequence,payload,digest FROM csv_obligation_notes_v1
            WHERE obligation_id=? ORDER BY sequence LIMIT ?""",(key,MAX_NOTES+1)).fetchall()
        if len(rows)>MAX_NOTES:
            raise ValueError("obligation notes exceed capacity")
        head=record["registration_sha256"]
        previous_stamp=record["created_at"]
        notes=[]
        seen=set()
        for sequence,row in enumerate(rows,1):
            note=_note(row,record,head,sequence,seen,now)
            if _timestamp(note["recorded_at"])<_timestamp(previous_stamp):
                raise ValueError("obligation note time regression")
            previous_stamp=note["recorded_at"]
            head=note["event_sha256"]
            seen.add(note["reference"])
            notes.append(note)
        return dict(record,head_sha256=head,notes=notes,
                    state="LOCAL_EVIDENCE_NOTED" if notes else "LOCAL_ARTIFACT_RECORDED",
                    historical_only=True,**dict.fromkeys(_FLAGS_EXTRA,False))

    def register(self,result,*,now,confirmed=None,halted=None,halt_check=None,scout_review=None):
        """Trusted caller matched selected bytes; optional freshly derived Scout provenance."""
        _permit(halted,halt_check)
        if confirmed is not True:
            raise PermissionError("explicit obligation registration required")
        now=_now(now)
        binding=_binding(result["contract"],result["report"],artifact_reference(result))
        key=_head(binding)
        plan_id=binding["contract"]["plan_id"]
        stamp=_stamp(now)
        if now<_timestamp(binding["contract"]["context"]["retrieved_at"]):
            raise ValueError("obligation predates source")
        data=dict(binding=binding,created_at=stamp)
        if scout_review is not None:
            data["scout_review"]=validate_provenance(scout_review,binding["contract"],
                                                     binding["qa_report"],stamp)
        payload=_json(data)
        if len(payload)>MAX_PAYLOAD:
            raise ValueError("obligation payload too large")
        with self._transaction(write=True,halted=halted,halt_check=halt_check):
            present=self.db.execute("SELECT 1 FROM csv_obligations_v1 WHERE obligation_id=?",(key,)).fetchone()
            if present is None:
                if self.db.execute("SELECT COUNT(*) FROM csv_obligations_v1").fetchone()[0]>=MAX_OBLIGATIONS:
                    raise ValueError("obligation capacity review required")
                self.db.execute("INSERT INTO csv_obligations_v1 VALUES (?,?,?,?,?)",
                                (key,plan_id,stamp,payload,_digest(payload)))
            record=self._read(plan_id,key,now)
            if _json(record["binding"])!=_json(binding):
                raise ValueError("conflicting obligation identity")
            if scout_review is not None:
                # The existing content-addressed obligation ID stays unchanged.
                # Never rewrite a legacy registration, create a duplicate, or
                # change the provenance (and therefore its evidence-note head).
                stored=record.get("scout_review")
                if stored is None or stored["review_scope_sha256"]!=data["scout_review"]["review_scope_sha256"]:
                    raise ValueError("existing obligation has different or absent Scout provenance")
        return record

    def history(self,plan_id,key,*,now,halted=None,halt_check=None):
        now=_now(now)
        with self._transaction(write=False,halted=halted,halt_check=halt_check):
            return self._read(plan_id,key,now)

    @staticmethod
    def empty_list(plan_id,limit):
        _hash(plan_id)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid obligation history limit")
        return dict(plan_id=plan_id,rows=[],truncated=False,historical_only=True,
                    **dict.fromkeys(_FLAGS_EXTRA,False))

    def list_plan(self,plan_id,*,limit=100,now,halted=None,halt_check=None):
        report=self.empty_list(plan_id,limit)
        now=_now(now)
        with self._transaction(write=False,halted=halted,halt_check=halt_check):
            keys=self.db.execute("""SELECT obligation_id FROM csv_obligations_v1
                WHERE plan_id=? ORDER BY created_at DESC,obligation_id LIMIT ?""",
                (plan_id,limit+1)).fetchall()
            report["truncated"]=len(keys)>limit
            for (key,) in keys[:limit]:
                _permit(halted,halt_check)
                report["rows"].append(self._read(plan_id,key,now))
        return report

    def note(self,plan_id,key,*,kind,reference,expected_head,now,confirmed=None,
             halted=None,halt_check=None):
        _permit(halted,halt_check)
        if confirmed is not True:
            raise PermissionError("explicit local note confirmation required")
        if type(kind) is not str or kind not in NOTE_KINDS:
            raise ValueError("unknown evidence note kind")
        _hash(expected_head)
        parse_reference(reference)
        now=_now(now)
        with self._transaction(write=True,halted=halted,halt_check=halt_check):
            record=self._read(plan_id,key,now)
            if record["head_sha256"]!=expected_head:
                raise ValueError("obligation changed; refresh before recording evidence")
            notes=record["notes"]
            if len(notes)>=MAX_NOTES or any(row["reference"]==reference for row in notes):
                raise ValueError("duplicate evidence or note capacity reached")
            prior=notes[-1]["recorded_at"] if notes else record["created_at"]
            if now<_timestamp(prior):
                raise ValueError("obligation note time regression")
            event=dict(obligation_id=key,sequence=len(notes)+1,previous_sha256=expected_head,
                       kind=kind,reference=reference,recorded_at=_stamp(now))
            payload=_json(event)
            self.db.execute("INSERT INTO csv_obligation_notes_v1 VALUES (?,?,?,?)",
                            (key,event["sequence"],payload,_digest(payload)))
            return self._read(plan_id,key,now)
