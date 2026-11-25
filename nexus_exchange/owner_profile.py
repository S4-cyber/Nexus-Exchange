"""Local, owner-declared research capabilities; never identity or authorization."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
import sqlite3
from .governor import Action, decide

PROFILE_SOURCES=("sam","ted","uk_tender","canada","usaspending")
FIELDS={"mode","budget","hours_per_week","sources","naics","cpv","keywords"}

def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)

def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)

def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()

def _values(raw,pattern,limit=32):
    if type(raw) is not list or len(raw)>limit:
        raise ValueError("invalid bounded profile list")
    result=[]
    for value in raw:
        if type(value) is not str or not re.fullmatch(pattern,value):
            raise ValueError("invalid profile value")
        result.append(value)
    if len(set(result))!=len(result):
        raise ValueError("duplicate profile value")
    return sorted(result)

def normalize_profile(raw):
    if type(raw) is not dict or set(raw)!=FIELDS:
        raise ValueError("invalid profile schema")
    mode=raw["mode"]
    budget=raw["budget"]
    hours=raw["hours_per_week"]
    if mode not in ("genesis","catalyst") or type(mode) is not str:
        raise ValueError("invalid pathway")
    if type(budget) is not str or not re.fullmatch("[0-9]{1,12}(?:\\.[0-9]{1,2})?",budget):
        raise ValueError("invalid USD planning budget")
    value=Decimal(budget)
    if mode=="genesis" and value!=0:
        raise ValueError("Genesis requires zero planning budget")
    if type(hours) is not int or not 0<=hours<=168:
        raise ValueError("invalid weekly availability")
    sources=_values(raw["sources"],"[a-z_]{2,32}",len(PROFILE_SOURCES))
    if not set(sources)<=set(PROFILE_SOURCES):
        raise ValueError("unsupported profile source")
    keywords=_values(raw["keywords"],"[a-z0-9][a-z0-9 -]{1,47}",24)
    if any(k!=k.strip() for k in keywords):
        raise ValueError("invalid keyword whitespace")
    return dict(mode=mode,budget=format(value,".2f"),hours_per_week=hours,sources=sources,
        naics=_values(raw["naics"],"[0-9]{6}"),
        cpv=_values(raw["cpv"],"[0-9]{2,8}"),keywords=keywords)

def profile_revision(profile):
    return _digest(_json(normalize_profile(profile)))

class ProfileStore:
    """One explicit owner-declared local profile, no credentials or personal data."""
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS owner_profile_v1(
                slot INTEGER PRIMARY KEY CHECK(slot=1),payload TEXT NOT NULL,digest TEXT NOT NULL)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    def load(self,*,halted=None):
        _permit(halted)
        row=self.db.execute("SELECT payload,digest FROM owner_profile_v1 WHERE slot=1").fetchone()
        if row is None:
            return None
        encoded,digest=row
        if type(encoded) is not str or len(encoded)>8192 or _digest(encoded)!=digest:
            raise ValueError("profile integrity mismatch")
        value=normalize_profile(json.loads(encoded))
        if _json(value)!=encoded:
            raise ValueError("noncanonical stored profile")
        return value

    def save(self,profile,*,halted=None):
        _permit(halted)
        profile=normalize_profile(profile)
        encoded=_json(profile)
        digest=_digest(encoded)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("""INSERT INTO owner_profile_v1 VALUES (1,?,?)
                ON CONFLICT(slot) DO UPDATE SET payload=excluded.payload,digest=excluded.digest""",
                (encoded,digest))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return digest

    def clear(self,*,halted=None):
        _permit(halted)
        self.db.execute("DELETE FROM owner_profile_v1 WHERE slot=1")

def reported_codes(source,lead):
    """Retain only explicitly reported codes, never the search filter as evidence."""
    if "reported_codes" in lead:
        raw=lead["reported_codes"]
        if type(raw) is not list or len(raw)>100:
            raise ValueError("invalid reported classifications")
        codes=[]
        for entry in raw:
            if type(entry) is not dict or set(entry)!={"scheme","code"}:
                raise ValueError("invalid classification")
            scheme,code=entry["scheme"],entry["code"]
            allowed={"sam":"NAICS","ted":"CPV"}.get(source)
            if allowed is None or scheme!=allowed or type(code) is not str or not re.fullmatch(
                    "[0-9]{6}" if scheme=="NAICS" else "[0-9]{8}",code):
                raise ValueError("invalid source classification")
            codes.append((scheme,code))
        if len(set(codes))!=len(codes):
            raise ValueError("duplicate classifications")
    elif source=="sam" and type(lead.get("metadata")) is dict:
        code=lead["metadata"].get("naicsCode")
        codes=[("NAICS",code)] if type(code) is str and re.fullmatch("[0-9]{6}",code) else []
    elif source=="ted" and type(lead.get("classifications")) is list:
        raw=lead["classifications"]
        if len(raw)>100 or any(type(c) is not str or not re.fullmatch("[0-9]{8}",c) for c in raw):
            raise ValueError("invalid TED classifications")
        codes=[("CPV",c) for c in raw]
    else:
        codes=[]
    return [dict(scheme=s,code=c) for s,c in sorted(set(codes))]

BLOCKED_REASONS=frozenset({"OBSERVATION_STALE","OBSERVATION_IN_FUTURE","REPORTED_DEADLINE_PASSED",
    "REPORTED_DEADLINE_DATE_PASSED_OR_TODAY","LATER_UK_EVENT_IN_ARCHIVE",
    "AMBIGUOUS_UK_EVENT_IN_ARCHIVE","COLLECTION_WINDOW_INCOMPLETE"})

def assess_profile(profile,lead):
    """Deterministic review ordering, not verification, feasibility or a revenue score."""
    profile=normalize_profile(profile)
    if type(lead) is not dict or lead.get("source") not in PROFILE_SOURCES:
        raise ValueError("invalid source observation")
    source=lead["source"]
    if type(lead.get("title")) is not str or type(lead.get("blockers")) is not list:
        raise ValueError("invalid observation")
    codes=reported_codes(source,lead)
    comparable=[c for c in codes if profile["naics" if c["scheme"]=="NAICS" else "cpv"]]
    matches=[c for c in comparable if (
        c["code"] in profile["naics"] if c["scheme"]=="NAICS" else
        any(c["code"].startswith(prefix) for prefix in profile["cpv"]))]
    title=lead["title"].casefold()
    hints=[word for word in profile["keywords"] if re.search(
        r"(?<!\w)"+re.escape(word)+r"(?!\w)",title)]
    if source not in profile["sources"]:
        priority,reason=6,"SOURCE_NOT_SELECTED"
    elif source=="usaspending":
        priority,reason=5,"CONTRACTOR_INTELLIGENCE_ONLY"
    elif profile["hours_per_week"]==0:
        priority,reason=4,"NO_DECLARED_AVAILABILITY"
    elif not lead.get("research_candidate_at_collection") or BLOCKED_REASONS.intersection(lead["blockers"]):
        priority,reason=4,"REFRESH_OR_BLOCKED"
    elif matches:
        priority,reason=0,"DECLARED_CLASSIFICATION_MATCH"
    elif comparable:
        priority,reason=3,"CLASSIFICATION_MISMATCH"
    elif hints:
        priority,reason=1,"TITLE_HINT_ONLY"
    else:
        priority,reason=2,"NO_CAPABILITY_SIGNAL"
    return dict(priority=priority,reason=reason,matched_codes=matches,title_hints=hints,
        profile_revision=profile_revision(profile),declared_only=True,execution_eligible=False,
        external_authority=False,cash_exposure=None)

PROFILE_TASKS=(
    ("capability_profile","Verify actual requirements against declared services, skill and availability."),
    ("capital_profile","Confirm actual cash exposure and payment terms against the planning pathway; no spending authorized."),
)

def rank_history(profile,leads):
    profile=normalize_profile(profile)
    if type(leads) is not list or len(leads)>10000:
        raise ValueError("invalid bounded history")
    rows=[]
    for lead in leads:
        fit=assess_profile(profile,lead)
        tasks=list(lead["todo"])+[dict(key=k,instruction=t,status="needs independent evidence")
            for k,t in PROFILE_TASKS]
        rows.append(dict(lead,profile_fit=fit,todo=tasks))
    # Stable sorting preserves existing newest-first ordering within each tier.
    rows.sort(key=lambda row:row["profile_fit"]["priority"])
    return rows
