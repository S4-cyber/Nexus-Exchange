"""Completed capability-search receipts and advisory repeat detection.

Stored atomically with the corresponding archive observations. No API key,
raw provider report, personal profile, source text or automatic replay.
Local hashes establish consistency, not authenticated search evidence.
"""
from datetime import date, timedelta
import json
import re

from .lead_store import ArchiveCapacityError, _json, _digest, _now, _permit, _hashes, MAX_BATCH, SOURCES, _restore, MAX_AGE
from .scout import _timestamp

LEGACY_FORMAT="nexus-scout-search-receipt-v1"
FORMAT="nexus-scout-search-receipt-v2"
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
    if type(payload) is not dict:
        raise ValueError("Invalid search receipt schema.")
    version=payload.get("format")
    if not ((version==LEGACY_FORMAT and set(payload)==_FIELDS) or
            (version==FORMAT and set(payload)==_FIELDS|{"observation_refs"})):
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
    if version==FORMAT:
        refs=payload["observation_refs"]
        if type(refs) is not list or len(refs)!=payload["returned"]:
            raise ValueError("Invalid search observation references.")
        identities=set()
        for ref in refs:
            if type(ref) is not list or len(ref)!=4 or ref[0]!=source:
                raise ValueError("Invalid search observation reference.")
            _hash(ref[1])
            _hash(ref[3])
            if not start<=_stamp(ref[2])<=end:
                raise ValueError("Observation reference outside search interval.")
            if ref[1] in identities:
                raise ValueError("Duplicate search observation reference.")
            identities.add(ref[1])
        if refs!=sorted(refs) or _digest(_json(refs))!=payload["observations_sha256"]:
            raise ValueError("Search observation set digest mismatch.")
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
    refs=sorted([source,key,stamp,digest] for source,key,stamp,_encoded,digest in records)
    scope=_scope(row)
    return _validate(dict(format=FORMAT,task_id=discovery["task_id"],
        plan_sha256=plan["plan_sha256"],option_id=row["option_id"],
        capability_id=plan["capability_id"],profile_revision=plan["profile_revision"],
        catalog_sha256=plan["catalog_sha256"],started_at=start.isoformat(timespec="microseconds"),
        completed_at=end.isoformat(timespec="microseconds"),scope=scope,filter_sha256=_filter(scope),
        requests=report.get("requests"),returned=report["returned"],inserted=inserted,
        truncated=report["truncated"],page_sha256=report["page_sha256"],
        observations_sha256=_digest(_json(refs)),observation_refs=refs,
        **dict.fromkeys(_FLAGS,False)))


def insert_receipt(db,discovery,report,records,inserted,*,now):
    """Called only inside the existing LeadStore archive transaction."""
    payload=make_receipt(discovery,report,records,inserted,now=now)
    encoded=_json(payload)
    if len(encoded)>MAX_PAYLOAD:
        raise ValueError("Search receipt exceeds bound.")
    if db.execute("SELECT COUNT(*) FROM scout_search_receipts_v1").fetchone()[0]>=MAX_RECEIPTS:
        raise ArchiveCapacityError("Search history capacity review required.")
    db.execute("INSERT INTO scout_search_receipts_v1 VALUES (?,?,?,?)",
               (payload["task_id"],payload["completed_at"],encoded,_digest(encoded)))


def _verify_archive(db,payload,cache):
    """Check only the bounded displayed receipts; never infer provider authenticity."""
    if payload["format"]==LEGACY_FORMAT:
        return False
    for source,key,stamp,digest in payload["observation_refs"]:
        identity=(source,key,stamp)
        if identity not in cache:
            row=db.execute("""SELECT payload,payload_sha256 FROM scout_observations_v1
                WHERE source=? AND lead_key=? AND retrieved_at=?""",identity).fetchone()
            if row is None:
                raise ValueError("Search receipt observation missing from archive.")
            restored=_restore(*row)
            if (restored["source"],restored["key"],restored["retrieved_at"])!=identity:
                raise ValueError("Search receipt observation identity mismatch.")
            cache[identity]=row[1]
        if cache[identity]!=digest:
            raise ValueError("Search receipt archive digest mismatch.")
    return True


def read_history(db,*,now,limit=100,halted=None):
    """Read receipt metadata and displayed archive references in one snapshot.

    Validate every bounded receipt, even beyond the display limit. Only
    displayed references are cross-checked; this is not a full archive audit.
    """
    _permit(halted)
    now=_now(now)
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("Invalid search history limit.")
    if db.in_transaction:
        raise ValueError("Search history requires an idle archive connection.")
    rows=[]
    cache={}
    total=0
    db.execute("BEGIN")
    try:
        cursor=db.execute("""SELECT task_id,completed_at,payload,payload_sha256
            FROM scout_search_receipts_v1 ORDER BY completed_at DESC,task_id LIMIT ?""",
            (MAX_RECEIPTS+1,))
        try:
            for task,stamp,encoded,digest in cursor:
                total+=1
                if total>MAX_RECEIPTS:
                    raise ValueError("Search history exceeds bound.")
                if type(encoded) is not str or len(encoded)>MAX_PAYLOAD or _digest(encoded)!=digest:
                    raise ValueError("Search receipt digest mismatch.")
                value=_validate(json.loads(encoded))
                if _json(value)!=encoded or (value["task_id"],value["completed_at"])!=(task,stamp):
                    raise ValueError("Search receipt identity mismatch.")
                if len(rows)<limit:
                    rows.append(dict(value,receipt_sha256=digest,
                                     local_archive_consistent=_verify_archive(db,value,cache),
                                     historical_only=True,future_dated=_stamp(stamp)>now))
        finally:
            cursor.close()
        return dict(format="nexus-scout-search-history-v1",rows=rows,
            returned=len(rows),total=total,truncated=len(rows)<total,
            evaluated_at=now.isoformat(timespec="microseconds"),external_authority=False)
    finally:
        db.rollback()


def review_receipt(db,task_id,expected_sha256,*,now,halted=None):
    """Inspect exact referenced observations and same-identity archive drift.

    All reads share one SQLite snapshot. The selected receipt must still
    match its displayed digest. This does not authenticate the provider or
    establish that a source is open, current, or eligible for execution.
    """
    _permit(halted)
    now=_now(now)
    _hash(task_id,32)
    _hash(expected_sha256)
    if db.in_transaction:
        raise ValueError("Receipt review requires an idle archive connection.")
    db.execute("BEGIN")
    try:
        row=db.execute("""SELECT completed_at,payload,payload_sha256
            FROM scout_search_receipts_v1 WHERE task_id=?""",(task_id,)).fetchone()
        if row is None:
            raise ValueError("Selected search receipt not found.")
        stamp,encoded,digest=row
        if (type(encoded) is not str or len(encoded)>MAX_PAYLOAD
                or digest!=expected_sha256 or _digest(encoded)!=digest):
            raise ValueError("Selected search receipt changed.")
        value=_validate(json.loads(encoded))
        if (_json(value)!=encoded or (value["task_id"],value["completed_at"])!=(task_id,stamp)
                or _stamp(stamp)>now or value["format"]!=FORMAT):
            raise ValueError("Exact nonfuture v2 search receipt required.")
        _verify_archive(db,value,{})
        observations=[]
        for source,key,retrieved,ref_digest in value["observation_refs"]:
            exact=db.execute("""SELECT payload,payload_sha256 FROM scout_observations_v1
                WHERE source=? AND lead_key=? AND retrieved_at=?""",
                (source,key,retrieved)).fetchone()
            p=_restore(*exact)
            latest=db.execute("""SELECT retrieved_at,payload,payload_sha256
                FROM scout_observations_v1 WHERE source=? AND lead_key=?
                ORDER BY retrieved_at DESC LIMIT 1""",(source,key)).fetchone()
            latest_stamp,latest_payload,latest_digest=latest
            newest=_restore(latest_payload,latest_digest)
            if ((newest["source"],newest["key"],newest["retrieved_at"])!=(source,key,latest_stamp)
                    or _stamp(latest_stamp)<_stamp(retrieved)):
                raise ValueError("Latest archive observation identity mismatch.")
            if _stamp(latest_stamp)>now:
                state="FUTURE_OBSERVATION_KNOWN"
            elif latest_stamp!=retrieved:
                state="LATER_OBSERVATION_KNOWN"
            else:
                state="SAME_OBSERVATION"
            reasons=list(p["blockers"])+["HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED"]
            if now-_stamp(retrieved)>MAX_AGE:
                reasons.append("OBSERVATION_STALE")
            if state!="SAME_OBSERVATION":
                reasons.append(state)
            if p["deadline"] is not None and _timestamp(p["deadline"])<=now:
                reasons.append("REPORTED_DEADLINE_PASSED")
            elif (p["deadline"] is None and p["earliest_deadline_date"] is not None
                  and date.fromisoformat(p["earliest_deadline_date"])<=now.date()):
                reasons.append("REPORTED_DEADLINE_DATE_PASSED_OR_TODAY")
            observations.append(dict(source=source,key=key,notice_id=p["notice_id"],
                title=p["title"],source_url=p["source_url"],retrieved_at=retrieved,
                observation_sha256=ref_digest,latest_retrieved_at=latest_stamp,
                latest_observation_sha256=latest_digest,latest_state=state,
                blockers=list(dict.fromkeys(reasons)),historical_only=True,
                execution_eligible=False,external_authority=False))
        return dict(format="nexus-scout-receipt-review-v1",task_id=task_id,
            receipt_sha256=digest,completed_at=stamp,observations=observations,
            evaluated_at=now.isoformat(timespec="microseconds"),truncated=value["truncated"],
            historical_only=True,local_archive_consistent=True,
            provider_freshness_verified=False,independently_verified=False,
            execution_eligible=False,external_authority=False)
    finally:
        db.rollback()


def receipt_review_text(report):
    lines=["SCOUT — EXACT HISTORICAL SEARCH OBSERVATIONS",
           "Receipt: "+report["receipt_sha256"],"Completed UTC: "+report["completed_at"],
           "Reviewed UTC: "+report["evaluated_at"],
           "Local archive consistency only; source authenticity, freshness and eligibility are unverified.",
           "Later observations are compared only for the same source/key, not cross-release or cross-source identities.",
           "Collection was truncated." if report["truncated"] else "Collection was not marked truncated."]
    if not report["observations"]:
        lines.append("No observations recorded for this receipt; not proof of no available opportunity.")
    for index,item in enumerate(report["observations"],1):
        lines.extend(["",str(index)+". "+item["title"],
            item["source"]+" / "+item["notice_id"],item["source_url"],
            "Observed UTC: "+item["retrieved_at"],"Observation: "+item["observation_sha256"],
            "Latest same-identity UTC: "+item["latest_retrieved_at"]+" | "+item["latest_state"],
            "Latest same-identity digest: "+item["latest_observation_sha256"],
            "Review holds: "+", ".join(item["blockers"])])
    lines.extend(["","No automatic refresh, qualification, outreach or commitment."])
    return "\n".join(lines)


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
                    local_archive_consistent=row.get("local_archive_consistent") is True,
                    automatic_skip=False)
    return None


def hint_text(hint):
    if hint is None:
        return "Recent repeat check: no comparable receipt in the displayed history. Not proof this search is new."
    return ("Recent repeat check: "+hint["match"]+" | completed "+hint["completed_at"]
            +" | "+str(hint["returned"])+" returned, "+str(hint["inserted"])+" new observations"
            +(" | collection truncated" if hint["truncated"] else "")
            +(" | local archive references consistent" if hint.get("local_archive_consistent") is True
              else " | local archive references not verified")
            +"\nThis is historical research, not current source availability. You may still confirm a fresh search.")
