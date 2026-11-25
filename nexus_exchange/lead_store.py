"""Bounded historical source observations, never a current-tender or authority index."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
from types import MappingProxyType
from .governor import Action, decide
from .scout import _text, _timestamp, normalize
from .revenue_pathways import CHECKS
from .sam_search import notice_url as sam_url
from .ted_search import notice_url as ted_url
from .fts_search import notice_url as fts_url
from .cf_search import notice_url as cf_url
from .canada_search import notice_url as canada_url
from .usaspending_search import award_url, metadata as award_metadata, CONTRACTOR_TASKS
from .owner_profile import reported_codes, rank_history, profile_revision

SOURCES=MappingProxyType({
    "nexus-sam-research-v1":("sam",sam_url),
    "nexus-ted-research-v1":("ted",ted_url),
    "nexus-fts-research-v1":("uk_tender",fts_url),
    "nexus-cf-research-v1":("uk_contracts",cf_url),
    "nexus-canada-research-v1":("canada",canada_url),
    "nexus-usaspending-research-v1":("usaspending",award_url),
})
MAX_ROWS=10000
MAX_BATCH=75
MAX_AGE=timedelta(hours=24)
MAX_PAYLOAD=32768

def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)

def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()

def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)

def _now(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware time required")
    return now.astimezone(timezone.utc)

def _calendar(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch("[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValueError("invalid reported date")
    return date.fromisoformat(value).isoformat()

def _hashes(values):
    if type(values) is not list or not 1<=len(values)<=3 or any(
            type(v) is not str or not re.fullmatch("[0-9a-f]{64}",v) for v in values):
        raise ValueError("invalid page digests")
    return list(values)

def _project(fmt,lead,hashes,truncated):
    if type(lead) is not dict or fmt not in SOURCES:
        raise ValueError("unknown lead source")
    source,link_for=SOURCES[fmt]
    notice=lead.get("notice_id")
    url=link_for(notice)
    if lead.get("source_url")!=url:
        raise ValueError("noncanonical source link")
    if lead.get("execution_eligible") is not False or lead.get("external_authority") is not False or lead.get("cash_exposure") is not None:
        raise ValueError("authority or cost claims forbidden in historical source records")
    if type(lead.get("research_candidate")) is not bool or type(truncated) is not bool:
        raise ValueError("invalid historical screening")
    identity=notice
    if source=="ted":
        seq,year=notice.split("-")
        identity=str(int(seq))+"-"+year
    elif source in ("sam","canada"):
        identity=notice.casefold()
    stamp=_timestamp(lead.get("retrieved_at"))
    deadline=lead.get("deadline")
    op=normalize(dict(source=source,external_id=identity,title=lead.get("title"),
        source_url=url,retrieved_at=stamp.isoformat(),deadline=deadline,currency=None,amount=None))
    reasons=lead.get("blockers")
    if type(reasons) is not list or not 1<=len(reasons)<=64 or any(
            type(r) is not str or not re.fullmatch("[A-Z][A-Z0-9_]{0,95}",r) for r in reasons):
        raise ValueError("invalid reason codes")
    if "CASH_EXPOSURE_UNKNOWN" not in reasons or "OWNER_APPROVAL_REQUIRED" not in reasons:
        raise ValueError("required review blockers missing")
    ocid=None
    release_date=None
    if source in ("uk_tender","uk_contracts"):
        ocid=lead.get("ocid")
        if type(ocid) is not str or not re.fullmatch("ocds-[A-Za-z0-9-]{1,240}",ocid):
            raise ValueError("invalid UK process identity")
        release_date=_timestamp(lead.get("release_date")).isoformat()
    payload=dict(format=fmt,source=source,key=op.key,notice_id=notice,
        title=op.title,source_url=op.source_url,retrieved_at=stamp.isoformat(timespec="microseconds"),
        deadline=op.deadline.isoformat() if op.deadline else None,
        earliest_deadline_date=_calendar(lead.get("earliest_deadline_date")),
        ocid=ocid,release_date=release_date,
        research_candidate_at_collection=lead["research_candidate"],
        blockers=list(dict.fromkeys(reasons)),page_sha256=_hashes(hashes),
        collection_truncated=truncated)
    if source=="usaspending":
        if lead["research_candidate"] or deadline is not None or payload["earliest_deadline_date"] is not None or "HISTORICAL_AWARD_NOT_SOLICITATION" not in reasons:
            raise ValueError("award intelligence cannot be tender eligibility")
        payload["award_metadata"]=award_metadata(lead.get("award_metadata"))
        if payload["award_metadata"]["recipient"]!=op.title:
            raise ValueError("award recipient mismatch")
    codes=reported_codes(source,lead)
    if codes:
        payload["reported_codes"]=codes
    encoded=_json(payload)
    if len(encoded)>MAX_PAYLOAD:
        raise ValueError("lead payload exceeds limit")
    return payload,encoded

def _restore(encoded,digest):
    if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
        raise ValueError("stored observation integrity mismatch")
    p=json.loads(encoded)
    lead=dict(p,research_candidate=p["research_candidate_at_collection"],
        execution_eligible=False,external_authority=False,cash_exposure=None)
    restored,canonical=_project(p["format"],lead,p["page_sha256"],p["collection_truncated"])
    if canonical!=encoded:
        raise ValueError("stored observation schema mismatch")
    return restored

class LeadStore:
    """Trusted single-user local database. No credentials or raw provider reports."""
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS scout_observations_v1(
                source TEXT NOT NULL, lead_key TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                PRIMARY KEY(source,lead_key,retrieved_at))""")
            self.db.execute("""CREATE INDEX IF NOT EXISTS scout_recent_v1
                ON scout_observations_v1(retrieved_at DESC,source,lead_key)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self
    def __exit__(self,*exc):
        self.db.close()

    def record(self,report,*,now,halted=None):
        _permit(halted)
        now=_now(now)
        if type(report) is not dict or report.get("format") not in SOURCES:
            raise ValueError("supported source report required")
        rows=report.get("leads")
        if type(rows) is not list or len(rows)>MAX_BATCH or type(report.get("returned")) is not int or report["returned"]!=len(rows):
            raise ValueError("invalid report count")
        hashes=_hashes(report.get("page_sha256"))
        truncated=report.get("truncated")
        if type(truncated) is not bool:
            raise ValueError("invalid truncation state")
        records=[]
        seen=set()
        for lead in rows:
            p,encoded=_project(report["format"],lead,hashes,truncated)
            if _timestamp(p["retrieved_at"])>now:
                raise ValueError("future observation")
            identity=(p["source"],p["key"])
            if identity in seen:
                raise ValueError("duplicate source identity in report")
            seen.add(identity)
            records.append((*identity,p["retrieved_at"],encoded,_digest(encoded)))
        inserted=0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            count=self.db.execute("SELECT COUNT(*) FROM scout_observations_v1").fetchone()[0]
            for source,key,stamp,payload,digest in records:
                prior=self.db.execute("""SELECT payload,payload_sha256 FROM scout_observations_v1
                    WHERE source=? AND lead_key=? AND retrieved_at=?""",(source,key,stamp)).fetchone()
                if prior is not None:
                    if prior!=(payload,digest):
                        raise ValueError("conflicting observation at same retrieval time")
                    continue
                if count+inserted>=MAX_ROWS:
                    raise ValueError("lead archive capacity review required")
                self.db.execute("INSERT INTO scout_observations_v1 VALUES (?,?,?,?,?)",
                    (source,key,stamp,payload,digest))
                inserted+=1
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return inserted

    def browse(self,*,now,source=None,query="",limit=100,profile=None,lead_key=None,halted=None):
        _permit(halted)
        now=_now(now)
        if source is not None and (type(source) is not str or source not in {v[0] for v in SOURCES.values()}):
            raise ValueError("invalid source filter")
        if lead_key is not None and (source is None or type(lead_key) is not str or not re.fullmatch("[0-9a-f]{64}",lead_key)):
            raise ValueError("exact lookup requires source and valid lead key")
        if type(query) is not str or len(query)>120 or any(ord(c)<32 for c in query):
            raise ValueError("invalid search query")
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid output limit")
        # The storage cap also bounds validation and latest-per-identity projection.
        records=self.db.execute("""SELECT source,lead_key,retrieved_at,payload,payload_sha256
            FROM scout_observations_v1 ORDER BY retrieved_at DESC,source,lead_key LIMIT ?""",(MAX_ROWS+1,)).fetchall()
        if len(records)>MAX_ROWS:
            raise ValueError("archive exceeds configured capacity")
        latest={}
        for src,key,stamp,encoded,digest in records:
            p=_restore(encoded,digest)
            if (p["source"],p["key"],p["retrieved_at"])!=(src,key,stamp):
                raise ValueError("stored identity mismatch")
            latest.setdefault((src,key),p)
        # Detect later known UK events across search sessions, without compiling them.
        uk_latest={}
        uk_ties={}
        for p in latest.values():
            if p["ocid"] is not None:
                stamp=_timestamp(p["release_date"])
                prior=uk_latest.get(p["ocid"])
                if prior is None or stamp>prior:
                    uk_latest[p["ocid"]]=stamp
                    uk_ties[p["ocid"]]=1
                elif stamp==prior:
                    uk_ties[p["ocid"]]+=1
        output=[]
        needle=query.casefold()
        for p in latest.values():
            if source is not None and p["source"]!=source:
                continue
            if lead_key is not None and p["key"]!=lead_key:
                continue
            if needle not in " ".join((p["title"],p["notice_id"],p["source"])).casefold():
                continue
            reasons=list(p["blockers"])+["HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED"]
            stamp=_timestamp(p["retrieved_at"])
            if stamp>now:
                reasons.append("OBSERVATION_IN_FUTURE")
            elif now-stamp>MAX_AGE:
                reasons.append("OBSERVATION_STALE")
            if p["deadline"] is not None and _timestamp(p["deadline"])<=now:
                reasons.append("REPORTED_DEADLINE_PASSED")
            elif p["deadline"] is None and p["earliest_deadline_date"] is not None and date.fromisoformat(p["earliest_deadline_date"])<=now.date():
                reasons.append("REPORTED_DEADLINE_DATE_PASSED_OR_TODAY")
            if p["ocid"] is not None:
                if _timestamp(p["release_date"])<uk_latest[p["ocid"]]:
                    reasons.append("LATER_UK_EVENT_IN_ARCHIVE")
                elif uk_ties[p["ocid"]]>1:
                    reasons.append("AMBIGUOUS_UK_EVENT_IN_ARCHIVE")
            output.append(dict(p,observation_sha256=_digest(_json(p)),blockers=list(dict.fromkeys(reasons)),research_candidate=False,
                execution_eligible=False,external_authority=False,cash_exposure=None,
                todo=[dict(key=k,instruction=t,status="needs independent evidence") for k,t in (CONTRACTOR_TASKS if p["source"]=="usaspending" else CHECKS)]))
        if profile is not None:
            output=rank_history(profile,output)
        return dict(format="nexus-scout-history-v1",scope="Historical source observations; no current eligibility or authority",
            evaluated_at=now.isoformat(),source_filter=source,profile_revision=profile_revision(profile) if profile is not None else None,
            matched=len(output),returned=min(len(output),limit),
            truncated=len(output)>limit,leads=output[:limit])
