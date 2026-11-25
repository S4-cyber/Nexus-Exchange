"""Local owner review notes bound to exact historical observation and profile.
No state here constitutes independent verification or action authorization.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from .governor import Action, decide
from .owner_profile import PROFILE_SOURCES, PROFILE_TASKS
from .revenue_pathways import CHECKS
from .usaspending_search import CONTRACTOR_TASKS
from .scout import _timestamp

STATES=("pending","needs_followup","evidence_noted")
MAX_CONTEXTS=10000
MAX_PAYLOAD=16384
FIELDS={"version","source","lead_key","retrieved_at","observation_sha256","profile_revision"}

def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)

def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)

def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()

def _hash(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}",value):
        raise ValueError("invalid context digest")
    return value

def _context(raw):
    if type(raw) is not dict or set(raw)!=FIELDS or type(raw["version"]) is not int or raw["version"]!=1:
        raise ValueError("invalid checklist context")
    source=raw["source"]
    if type(source) is not str or source not in PROFILE_SOURCES:
        raise ValueError("invalid source")
    return dict(version=1,source=source,lead_key=_hash(raw["lead_key"]),
        retrieved_at=_timestamp(raw["retrieved_at"]).isoformat(timespec="microseconds"),
        observation_sha256=_hash(raw["observation_sha256"]),
        profile_revision=None if raw["profile_revision"] is None else _hash(raw["profile_revision"]))

def _definitions(context):
    base=CONTRACTOR_TASKS if context["source"]=="usaspending" else CHECKS
    return base+(PROFILE_TASKS if context["profile_revision"] is not None else ())

def context_for(lead):
    if type(lead) is not dict or any(lead.get(k) is not False for k in
            ("research_candidate","execution_eligible","external_authority")):
        raise ValueError("historical research projection required")
    fit=lead.get("profile_fit")
    if fit is not None and (type(fit) is not dict or "profile_revision" not in fit):
        raise ValueError("invalid profile fit")
    context=_context(dict(version=1,source=lead.get("source"),lead_key=lead.get("key"),
        retrieved_at=lead.get("retrieved_at"),observation_sha256=lead.get("observation_sha256"),
        profile_revision=fit["profile_revision"] if fit is not None else None))
    tasks=lead.get("todo")
    if type(tasks) is not list or any(type(t) is not dict for t in tasks) or [
            (t.get("key"),t.get("instruction")) for t in tasks]!=list(_definitions(context)):
        raise ValueError("checklist definitions changed")
    return context

def _entry(state,reference,stamp,context):
    if type(state) is not str or state not in STATES:
        raise ValueError("unknown review state")
    if type(reference) is not str or len(reference)>240 or any(not c.isprintable() for c in reference):
        raise ValueError("invalid evidence reference")
    reference=reference.strip()
    if state=="pending" and reference:
        raise ValueError("pending state cannot retain a reference")
    if state=="evidence_noted" and not reference:
        raise ValueError("evidence reference required")
    stamp=_timestamp(stamp)
    if stamp<_timestamp(context["retrieved_at"]):
        raise ValueError("review predates observation")
    return dict(state=state,reference=reference,recorded_at=stamp.isoformat(timespec="microseconds"))

def _decode(encoded,digest,context):
    if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
        raise ValueError("checklist integrity mismatch")
    data=json.loads(encoded)
    if type(data) is not dict or set(data)!={"context","generation","entries"} or data["context"]!=context:
        raise ValueError("checklist context mismatch")
    generation=data["generation"]
    entries=data["entries"]
    if type(generation) is not int or not 1<=generation<=1000000000 or type(entries) is not dict:
        raise ValueError("invalid checklist revision")
    if not set(entries)<={k for k,_ in _definitions(context)}:
        raise ValueError("unknown stored task")
    restored={}
    for key,entry in entries.items():
        if type(entry) is not dict or set(entry)!={"state","reference","recorded_at"}:
            raise ValueError("invalid stored task")
        restored[key]=_entry(entry["state"],entry["reference"],entry["recorded_at"],context)
    canonical=dict(context=context,generation=generation,entries=restored)
    if _json(canonical)!=encoded:
        raise ValueError("noncanonical checklist")
    return canonical

class ChecklistStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS scout_checklists_v1(
                scope TEXT PRIMARY KEY,payload TEXT NOT NULL,digest TEXT NOT NULL)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    def _read(self,context):
        scope=_digest(_json(context))
        row=self.db.execute("SELECT payload,digest FROM scout_checklists_v1 WHERE scope=?",(scope,)).fetchone()
        if row is None:
            return scope,None,dict(context=context,generation=0,entries={})
        return scope,row[1],_decode(row[0],row[1],context)

    def load(self,context,*,halted=None):
        _permit(halted)
        context=_context(context)
        scope,revision,data=self._read(context)
        tasks=[]
        for key,instruction in _definitions(context):
            entry=data["entries"].get(key,dict(state="pending",reference="",recorded_at=None))
            tasks.append(dict(key=key,instruction=instruction,**entry,independently_verified=False))
        return dict(context=context,scope=scope,revision=revision,tasks=tasks,
            evidence_noted=sum(t["state"]=="evidence_noted" for t in tasks),
            total=len(tasks),independent_verification_complete=False,
            execution_eligible=False,external_authority=False)

    def save(self,context,task_key,state,reference,*,now,expected_revision,halted=None):
        _permit(halted)
        context=_context(context)
        if type(task_key) is not str or task_key not in {k for k,_ in _definitions(context)}:
            raise ValueError("unknown task")
        if expected_revision is not None:
            _hash(expected_revision)
        if type(now) is not datetime or now.utcoffset() is None:
            raise ValueError("aware review time required")
        stamp=now.astimezone(timezone.utc).isoformat(timespec="microseconds")
        entry=_entry(state,reference,stamp,context)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            scope,revision,data=self._read(context)
            if revision!=expected_revision:
                raise ValueError("checklist changed; reload before editing")
            if revision is None and self.db.execute("SELECT COUNT(*) FROM scout_checklists_v1").fetchone()[0]>=MAX_CONTEXTS:
                raise ValueError("checklist capacity review required")
            if data["generation"]>=1000000000:
                raise ValueError("checklist revision limit")
            if any(_timestamp(old["recorded_at"])>now for old in data["entries"].values()):
                raise ValueError("review clock moved backward")
            data["generation"]+=1
            data["entries"][task_key]=entry
            encoded=_json(data)
            if len(encoded)>MAX_PAYLOAD:
                raise ValueError("checklist payload exceeds limit")
            digest=_digest(encoded)
            self.db.execute("""INSERT INTO scout_checklists_v1 VALUES (?,?,?)
                ON CONFLICT(scope) DO UPDATE SET payload=excluded.payload,digest=excluded.digest""",
                (scope,encoded,digest))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return self.load(context,halted=halted)
