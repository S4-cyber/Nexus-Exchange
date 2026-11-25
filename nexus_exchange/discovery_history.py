"""Completed capability-search receipts and advisory repeat detection.

Stored atomically with the corresponding archive observations. No API key,
raw provider report, personal profile, source text or automatic replay.
Local hashes establish consistency, not authenticated search evidence.
"""
from datetime import timedelta
import json
import re

from .lead_store import _json, _digest, _now, _permit, _hashes, MAX_BATCH, SOURCES
from .scout import _timestamp

FORMAT="nexus-scout-search-receipt-v1"
MAX_RECEIPTS=2000
MAX_PAYLOAD=32768
RECENT=timedelta(minutes=15)
_FLAGS=("external_authority","execution_eligible","actual_opportunity_verified",
        "automatic_search_enabled","independently_verified")
_FILTER_FIELDS=("source","filter_kind","filter_value","procurement_type")
_SCOPE_FIELDS=(*_FILTER_FIELDS,"window_start","window_end")
_FIELDS={"format","task_id","plan_sha256","option_id","capability_id","profile_revision",
         "catalog_sha256","started_at","completed_at","scope","filter_sha256",
         "requests","returned","inserted","truncated","page_sha256","observations_sha256",*_FLAGS}
_ROUTES={"sam":("TITLE_KEYWORD",3),"ted":("DECLARED_CPV_PREFIX",3),
         "uk_contracts":("LOCAL_DECLARED_CPV_PREFIX",1),"uk_tender":("BROAD_RELEASE_WINDOW",3),
         "canada":("LOCAL_TITLE_SUBSTRING",1)}
_CAPABILITIES={"csv_preserve_and_standardize_v2","json_string_records_to_csv_v1",
               "csv_column_quality_profile_v1","csv_key_reconciliation_v1"}
_PHRASES={"csv sorting","json to csv","csv quality report","csv reconciliation"}


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS scout_search_receipts_v1(
        task_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL,
        payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS scout_search_recent_v1
        ON scout_search_receipts_v1(completed_at DESC,task_id)""")


def _hash(value,length=64):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{"+str(length)+"}",value):
        raise ValueError("Invalid search receipt identity.")
    return value


def _stamp(value):
    dt=_timestamp(value)
    if dt.isoformat(timespec="microseconds")!=value:
        raise ValueError("Invalid search receipt UTC time.")
    return dt


def _scope(row):
    return {key:row[key] for key in _SCOPE_FIELDS}


def _filter(scope):
    return _digest(_json({key:scope[key] for key in _FILTER_FIELDS}))


def _scope_dates(scope):
    from datetime import date
    source=scope["source"]
    if source=="canada":
        if scope["window_start"] is not None or scope["window_end"] is not None:
            raise ValueError("Unexpected dataset query window.")
        return None,None
    if source in ("sam","ted"):
        for value in (scope["window_start"],scope["window_end"]):
            if type(value) is not str or not re.fullmatch("[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
                raise ValueError("Invalid search date.")
        start,end=map(date.fromisoformat,(scope["window_start"],scope["window_end"]))
        if end-start!=timedelta(days=14):
            raise ValueError("Invalid historical date span.")
    else:
        start,end=map(_timestamp,(scope["window_start"],scope["window_end"]))
        expected=timedelta(days=1) if source=="uk_tender" else timedelta(hours=6)
        if end-start!=expected or start.microsecond or end.microsecond:
            raise ValueError("Invalid historical time span.")
    return start,end


def _validate(payload):
    if type(payload) is not dict or set(payload)!=_FIELDS or payload["format"]!=FORMAT:
        raise ValueError("Invalid search receipt schema.")
    _hash(payload["task_id"],32)
    for key in ("plan_sha256","option_id","profile_revision","catalog_sha256",
                "filter_sha256","observations_sha256"):
        _hash(payload[key])
    if type(payload["capability_id"]) is not str or payload["capability_id"] not in _CAPABILITIES:
        raise ValueError("Invalid historical capability.")
    start,end=_stamp(payload["started_at"]),_stamp(payload["completed_at"])
    if end<start:
        raise ValueError("Search receipt time reversed.")
    if any(payload[key] is not False for key in _FLAGS) or type(payload["truncated"]) is not bool:
        raise ValueError("Invalid search receipt authority.")
    scope=payload["scope"]
    if type(scope) is not dict or set(scope)!=set(_SCOPE_FIELDS):
        raise ValueError("Invalid search scope.")
    source=scope["source"]
    if type(source) is not str or source not in _ROUTES or scope["filter_kind"]!=_ROUTES[source][0]:
        raise ValueError("Invalid search route.")
    value=scope["filter_value"]
    ptype=scope["procurement_type"]
    if source in ("sam","canada"):
        if type(value) is not str or value not in _PHRASES:
            raise ValueError("Unexpected historical search phrase.")
    elif source in ("ted","uk_contracts"):
        if type(value) is not str or not re.fullmatch("[0-9]{2,8}",value):
            raise ValueError("Invalid historical CPV.")
    elif value is not None:
        raise ValueError("Unexpected broad-release filter.")
    if (source=="sam" and ptype not in ("k","o")) or (source!="sam" and ptype is not None):
        raise ValueError("Invalid historical procurement type.")
    _scope_dates(scope)
    if _filter(scope)!=payload["filter_sha256"]:
        raise ValueError("Search filter identity mismatch.")
    for key,low,high in (("requests",1,_ROUTES[source][1]),("returned",0,MAX_BATCH),
                         ("inserted",0,MAX_BATCH)):
        if type(payload[key]) is not int or not low<=payload[key]<=high:
            raise ValueError("Invalid search receipt count.")
    hashes=_hashes(payload["page_sha256"])
    if payload["inserted"]>payload["returned"] or len(hashes)>payload["requests"]:
        raise ValueError("Inconsistent search receipt counts.")
    return payload


def make_receipt(discovery,report,records,inserted,*,now):
    """Use the exact plan as of dispatch, and bind the parsed archive projection."""
    from .scout_discovery import resolve_query
    if type(discovery) is not dict or set(discovery)!={"plan","option_id","profile","started_at","task_id"}:
        raise ValueError("Exact discovery receipt context required.")
    plan=discovery["plan"]
    start=_now(discovery["started_at"])
    end=_now(now)
    row,query=resolve_query(plan,discovery["option_id"],discovery["profile"],
                            now=start,halted=False)
    if SOURCES[report["format"]][0]!=row["source"]:
        raise ValueError("Discovery report source differs from selected search.")
    expected=({"title_keyword":query.validated()} if row["source"]=="canada"
              else query.parameters(start))
    if _json(report.get("query"))!=_json(expected):
        raise ValueError("Discovery report query differs from selected search.")
    if row["source"]=="uk_contracts" and report.get("local_cpv_prefix")!=row["filter_value"]:
        raise ValueError("Discovery report local CPV differs from selected search.")
    if len(records)!=report["returned"]:
        raise ValueError("Discovery archive count mismatch.")
    refs=sorted((source,key,stamp,digest) for source,key,stamp,_encoded,digest in records)
    if any(_timestamp(stamp)<start for _,_,stamp,_ in refs):
        raise ValueError("Observation predates the recorded discovery task.")
    scope=_scope(row)
    return _validate(dict(format=FORMAT,task_id=discovery["task_id"],
        plan_sha256=plan["plan_sha256"],option_id=row["option_id"],
        capability_id=plan["capability_id"],profile_revision=plan["profile_revision"],
        catalog_sha256=plan["catalog_sha256"],started_at=start.isoformat(timespec="microseconds"),
        completed_at=end.isoformat(timespec="microseconds"),scope=scope,filter_sha256=_filter(scope),
        requests=report.get("requests"),returned=report["returned"],inserted=inserted,
        truncated=report["truncated"],page_sha256=report["page_sha256"],
        observations_sha256=_digest(_json(refs)),**dict.fromkeys(_FLAGS,False)))


def insert_receipt(db,discovery,report,records,inserted,*,now):
    """Called only inside the existing LeadStore archive transaction."""
    payload=make_receipt(discovery,report,records,inserted,now=now)
    encoded=_json(payload)
    if len(encoded)>MAX_PAYLOAD:
        raise ValueError("Search receipt exceeds bound.")
    if db.execute("SELECT COUNT(*) FROM scout_search_receipts_v1").fetchone()[0]>=MAX_RECEIPTS:
        raise ValueError("Search history capacity review required.")
    db.execute("INSERT INTO scout_search_receipts_v1 VALUES (?,?,?,?)",
               (payload["task_id"],payload["completed_at"],encoded,_digest(encoded)))


def read_history(db,*,now,limit=100,halted=None):
    _permit(halted)
    now=_now(now)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("Invalid search history limit.")
    raw=db.execute("""SELECT task_id,completed_at,payload,payload_sha256
        FROM scout_search_receipts_v1 ORDER BY completed_at DESC,task_id LIMIT ?""",
        (MAX_RECEIPTS+1,)).fetchall()
    if len(raw)>MAX_RECEIPTS:
        raise ValueError("Search history exceeds bound.")
    rows=[]
    for task,stamp,encoded,digest in raw:
        if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
            raise ValueError("Search receipt digest mismatch.")
        value=_validate(json.loads(encoded))
        if _json(value)!=encoded or (value["task_id"],value["completed_at"])!=(task,stamp):
            raise ValueError("Search receipt identity mismatch.")
        if len(rows)<limit:
            rows.append(dict(value,receipt_sha256=digest,
                             historical_only=True,future_dated=_stamp(stamp)>now))
    return dict(format="nexus-scout-search-history-v1",rows=rows,
        returned=len(rows),total=len(raw),truncated=len(rows)<len(raw),
        evaluated_at=now.isoformat(timespec="microseconds"),external_authority=False)


def recent_hint(option,history,*,now):
    """Advisory exact/overlap hint, never a cache hit, block or freshness grant."""
    now=_now(now)
    scope=_scope(option)
    if option["source"] not in _ROUTES or option["state"]!="REVIEW_FOR_READ_CONSENT":
        return None
    key=_filter(scope)
    start,end=_scope_dates(scope)
    for row in history["rows"]:
        if row["filter_sha256"]!=key:
            continue
        completed=_stamp(row["completed_at"])
        if not timedelta(0)<=now-completed<=RECENT:
            continue
        previous=row["scope"]
        old_start,old_end=_scope_dates(previous)
        if scope==previous:
            match="EXACT_QUERY"
        elif start is not None and old_start is not None and max(start,old_start)<=min(end,old_end):
            match="OVERLAPPING_WINDOW"
        else:
            continue
        return dict(match=match,completed_at=row["completed_at"],returned=row["returned"],
                    inserted=row["inserted"],truncated=row["truncated"],
                    receipt_sha256=row["receipt_sha256"],freshness_verified=False,
                    automatic_skip=False)
    return None


def hint_text(hint):
    if hint is None:
        return "Recent repeat check: no comparable receipt in the displayed history. Not proof this search is new."
    return ("Recent repeat check: "+hint["match"]+" | completed "+hint["completed_at"]
            +" | "+str(hint["returned"])+" returned, "+str(hint["inserted"])+" new observations"
            +(" | collection truncated" if hint["truncated"] else "")
            +"\nThis is historical research, not current source availability. You may still confirm a fresh search.")
