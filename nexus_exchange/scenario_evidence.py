"""Immutable per-assumption file references, never factual evidence approval.

Trusted local storage; only explicit owner-selected files are read. A reference
records byte identity and an association with a saved hypothetical value, not
the meaning, origin or truth of a document.
"""
from contextlib import contextmanager
import json

from .cash_feasibility import COSTS
from .checklist_store import _hash
from .evidence import fingerprint, verify_reference, parse_reference, _permit
from .lead_store import _digest, _json, _now
from .scenario_store import ScenarioStore
from .schedule_feasibility import _iso
from .scout import _timestamp

FINANCIAL_FIELDS=("compensation","probability_delivery_bps",
    "probability_payment_given_delivery_bps","delivery_days",
    "payment_days_after_delivery","labor_hours")
SCHEDULE_FIELDS=("preparation_days","preparation_hours","delivery_start","delivery_deadline")
ASSUMPTION_FIELDS=FINANCIAL_FIELDS+tuple("cost:"+k for k in COSTS)+SCHEDULE_FIELDS
MAX_REFERENCES_PER_FIELD=3
MAX_EVIDENCE_ROWS=20000
MAX_PAYLOAD=2048
_BINDING_FIELDS={"version","plan_id","field","value_sha256","reference"}
_RECORD_FIELDS=_BINDING_FIELDS|{"created_at"}


def _field(field):
    if type(field) is not str or field not in ASSUMPTION_FIELDS:
        raise ValueError("unknown scenario assumption")
    return field


def _value(saved,field):
    _field(field)
    if field.startswith("cost:"):
        return saved["scenario"]["costs"][field[5:]]
    if field in FINANCIAL_FIELDS:
        return saved["scenario"][field]
    return saved["plan"][field]


def _binding(saved,field,reference):
    value=_value(saved,field)
    if value is None:
        raise ValueError("unknown assumption cannot have a value-bound reference")
    parse_reference(reference)
    value_digest=_digest(_json(dict(plan_id=saved["plan_id"],field=field,value=value)))
    return dict(version=1,plan_id=saved["plan_id"],field=field,
                value_sha256=value_digest,reference=reference)


def _decode(row,saved,now):
    evidence_id,plan_id,field,created_at,encoded,digest=row
    if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
        raise ValueError("stored evidence integrity mismatch")
    data=json.loads(encoded)
    if (type(data) is not dict or set(data)!=_RECORD_FIELDS
            or type(data["version"]) is not int or data["version"]!=1):
        raise ValueError("invalid stored evidence schema")
    binding=_binding(saved,_field(field),data["reference"])
    stamp=_timestamp(data["created_at"])
    if stamp<_timestamp(saved["created_at"]) or stamp>now:
        raise ValueError("stored evidence timestamp outside scenario review")
    canonical=dict(binding,created_at=_iso(stamp))
    if (_json(canonical)!=encoded or _digest(_json(binding))!=evidence_id
            or plan_id!=saved["plan_id"] or created_at!=canonical["created_at"]):
        raise ValueError("stored evidence identity mismatch")
    return dict(canonical,evidence_id=evidence_id,independently_verified=False,
                execution_eligible=False,external_authority=False)


class ScenarioEvidenceStore(ScenarioStore):
    """Bounded, additive associations to exact immutable scenario inputs."""
    def __init__(self,path):
        super().__init__(path)
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("""CREATE TABLE IF NOT EXISTS scout_assumption_evidence_v1(
                evidence_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL,
                field TEXT NOT NULL, created_at TEXT NOT NULL,
                payload TEXT NOT NULL, digest TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES scout_scenarios_v1(plan_id))""")
            self.db.execute("""CREATE INDEX IF NOT EXISTS scout_assumption_evidence_scope_v1
                ON scout_assumption_evidence_v1(plan_id,field,created_at,evidence_id)""")
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def _transaction(self,*,write=False,halted=None,halt_check=None):
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

    def _saved(self,plan_id,profile,now,halted,halt_check):
        _permit(halted,halt_check)
        saved=self.get(plan_id,halted=halted)
        if saved is None:
            raise ValueError("saved scenario unavailable")
        if _timestamp(saved["created_at"])>now:
            raise ValueError("review predates scenario")
        lead=self._current(saved["context"],profile,now,halted)
        _permit(halted,halt_check)
        return saved,lead

    def _references(self,saved,now):
        max_rows=len(ASSUMPTION_FIELDS)*MAX_REFERENCES_PER_FIELD
        rows=self.db.execute("""SELECT evidence_id,plan_id,field,created_at,payload,digest
            FROM scout_assumption_evidence_v1 WHERE plan_id=?
            ORDER BY field,created_at,evidence_id LIMIT ?""",
            (saved["plan_id"],max_rows+1)).fetchall()
        if len(rows)>max_rows:
            raise ValueError("stored evidence exceeds scenario capacity")
        grouped={field:[] for field in ASSUMPTION_FIELDS}
        for row in rows:
            entry=_decode(row,saved,now)
            items=grouped[entry["field"]]
            items.append(entry)
            if len(items)>MAX_REFERENCES_PER_FIELD:
                raise ValueError("stored evidence exceeds field capacity")
        return grouped

    def attach(self,plan_id,field,path,*,profile,now,halted=None,halt_check=None):
        _permit(halted,halt_check)
        now=_now(now)
        field=_field(field)
        # Validate the scope before touching the explicitly selected file.
        with self._transaction(halted=halted,halt_check=halt_check):
            saved,_=self._saved(plan_id,profile,now,halted,halt_check)
            if _value(saved,field) is None:
                raise ValueError("unknown assumption cannot be linked")
            self._references(saved,now)
        reference=fingerprint(path,halted=halted,halt_check=halt_check)
        # Do not hold SQLite's write lock during file I/O. Resolve again in
        # the insertion transaction to reject any superseding observation.
        with self._transaction(write=True,halted=halted,halt_check=halt_check):
            current,_=self._saved(plan_id,profile,now,halted,halt_check)
            binding=_binding(current,field,reference)
            key=_digest(_json(binding))
            grouped=self._references(current,now)
            prior=next((x for x in grouped[field] if x["evidence_id"]==key),None)
            if prior is not None:
                if {k:prior[k] for k in _BINDING_FIELDS}!=binding:
                    raise ValueError("conflicting immutable evidence")
                return key
            if len(grouped[field])>=MAX_REFERENCES_PER_FIELD:
                raise ValueError("assumption evidence capacity review required")
            if self.db.execute("SELECT COUNT(*) FROM scout_assumption_evidence_v1").fetchone()[0]>=MAX_EVIDENCE_ROWS:
                raise ValueError("archive evidence capacity review required")
            stamp=_iso(now)
            payload=_json(dict(binding,created_at=stamp))
            if len(payload)>MAX_PAYLOAD:
                raise ValueError("evidence payload exceeds limit")
            self.db.execute("INSERT INTO scout_assumption_evidence_v1 VALUES (?,?,?,?,?,?)",
                (key,plan_id,field,stamp,payload,_digest(payload)))
        return key

    def coverage(self,plan_id,*,profile,now,halted=None,halt_check=None):
        _permit(halted,halt_check)
        now=_now(now)
        with self._transaction(halted=halted,halt_check=halt_check):
            saved,lead=self._saved(plan_id,profile,now,halted,halt_check)
            grouped=self._references(saved,now)
            fields=[]
            for field in ASSUMPTION_FIELDS:
                value=_value(saved,field)
                refs=grouped[field]
                state=("ASSUMPTION_UNKNOWN" if value is None else
                       "REFERENCE_NOTED_UNVERIFIED" if refs else "REFERENCE_REQUIRED")
                fields.append(dict(field=field,value=value,state=state,references=refs,
                    independently_verified=False))
        return dict(format="nexus-scout-assumption-evidence-v1",plan_id=plan_id,
            context=saved["context"],evaluated_at=_iso(now),fields=fields,total=len(fields),
            referenced=sum(bool(f["references"]) for f in fields),
            unknown=sum(f["value"] is None for f in fields),
            independently_verified_count=0,independently_verified=False,
            source_blockers=tuple(lead["blockers"]),execution_eligible=False,
            genesis_verified=False,external_authority=False)

    def _attachment(self,plan_id,field,evidence_id,profile,now,halted,halt_check):
        saved,_=self._saved(plan_id,profile,now,halted,halt_check)
        refs=self._references(saved,now)[field]
        match=next((entry for entry in refs if entry["evidence_id"]==evidence_id),None)
        if match is None:
            raise ValueError("evidence reference outside exact scenario assumption")
        return match

    def verify_attachment(self,plan_id,field,evidence_id,path,*,profile,now,
                          halted=None,halt_check=None):
        _permit(halted,halt_check)
        now=_now(now)
        field=_field(field)
        _hash(evidence_id)
        with self._transaction(halted=halted,halt_check=halt_check):
            entry=self._attachment(plan_id,field,evidence_id,profile,now,halted,halt_check)
        result=verify_reference(path,entry["reference"],halted=halted,halt_check=halt_check)
        with self._transaction(halted=halted,halt_check=halt_check):
            current=self._attachment(plan_id,field,evidence_id,profile,now,halted,halt_check)
            if current!=entry:
                raise ValueError("evidence changed during byte comparison")
        # The byte result is ephemeral. No previous verdict is saved or
        # used as a current evidence or permission assertion.
        return dict(result,plan_id=plan_id,field=field,evidence_id=evidence_id,
                    value_sha256=entry["value_sha256"],evaluated_at=_iso(now),
                    genesis_verified=False)
