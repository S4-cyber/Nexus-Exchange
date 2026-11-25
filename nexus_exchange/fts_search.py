"""Bounded UK Find a Tender OCDS release discovery, not a current-state compiler."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import re
from time import sleep
from urllib.parse import urlencode, urlsplit, parse_qsl
from .governor import decide_fts_read
from .local_import import _pairs, _integer, _decimal, _constant
from .ocds_identity import release_identity
from .revenue_pathways import CHECKS
from .sam_search import SearchError
from .scout import _text, _timestamp

HOST = "www.find-tender.service.gov.uk"
PATH = "/api/1.0/ocdsReleasePackages"
FORMAT = "nexus-fts-research-v1"
PAGE_SIZE = 25
MAX_REQUESTS = 3
MAX_BYTES = 2 * 1024 * 1024
TENDER_TAGS = frozenset({"tender","tenderUpdate","tenderAmendment"})

@dataclass(frozen=True, slots=True)
class FtsQuery:
    updated_from: datetime
    updated_to: datetime

    def parameters(self, now):
        for value in (self.updated_from,self.updated_to,now):
            if type(value) is not datetime or value.utcoffset() is None:
                raise ValueError("aware timestamps required")
        start=self.updated_from.astimezone(timezone.utc)
        end=self.updated_to.astimezone(timezone.utc)
        if not timedelta(0)<end-start<=timedelta(days=7) or end>now:
            raise ValueError("choose a bounded historical update window (maximum 7 days)")
        # Provider's documented timezone-less syntax; UTC is an operational
        # assumption, not a claim about its undocumented boundary semantics.
        return dict(updatedFrom=start.strftime("%Y-%m-%dT%H:%M:%S"),
                    updatedTo=end.strftime("%Y-%m-%dT%H:%M:%S"),limit=str(PAGE_SIZE))

def notice_url(notice_id):
    if type(notice_id) is not str or not re.fullmatch("[0-9]{6}-[0-9]{4}",notice_id):
        raise ValueError("invalid UK notice ID")
    seq,year=notice_id.split("-")
    if not int(seq) or not 1900<=int(year)<=9999:
        raise ValueError("invalid UK notice ID")
    return "https://"+HOST+"/Notice/"+notice_id

def _request(params):
    connection=http.client.HTTPSConnection(HOST,443,timeout=10)
    try:
        connection.request("GET",PATH+"?"+urlencode(params),headers={
            "Accept":"application/json","Accept-Encoding":"identity",
            "User-Agent":"NexusExchange-Preview/1"})
        response=connection.getresponse()
        if response.status!=200:
            return response.status,b""
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise SearchError("FTS_RESPONSE_TOO_LARGE")
        return response.status,raw
    except SearchError:
        raise
    except Exception:
        raise SearchError("FTS_TRANSPORT_FAILURE") from None
    finally:
        connection.close()

def _next_cursor(package, base):
    links=package.get("links",{})
    if type(links) is not dict:
        raise ValueError("invalid pagination links")
    link=links.get("next")
    if link is None or link=="":
        return None
    if type(link) is not str or len(link)>4096 or "\\" in link or any(c.isspace() for c in link):
        raise ValueError("invalid next link")
    parsed=urlsplit(link)
    if parsed.scheme:
        if parsed.scheme!="https" or parsed.netloc!=HOST:
            raise ValueError("foreign continuation origin")
    elif parsed.netloc:
        raise ValueError("foreign continuation origin")
    if parsed.path!=PATH or parsed.fragment:
        raise ValueError("unexpected continuation route")
    pairs=parse_qsl(parsed.query,keep_blank_values=True,strict_parsing=True,max_num_fields=5)
    values=dict(pairs)
    if len(values)!=len(pairs) or not set(values)<=(set(base)|{"cursor"}):
        raise ValueError("unexpected continuation parameters")
    if any(values[k]!=base[k] for k in values if k!="cursor"):
        raise ValueError("changed query window")
    cursor=values.get("cursor")
    if type(cursor) is not str or not re.fullmatch("[A-Za-z0-9_+/=-]{1,300}",cursor):
        raise ValueError("invalid opaque cursor")
    # Do not follow provider URLs. Reconstruct only our fixed request.
    return cursor

def _notice(raw, now):
    if type(raw) is not dict:
        raise ValueError("invalid release")
    ocid=raw.get("ocid")
    if type(ocid) is not str or not re.fullmatch("ocds-[A-Za-z0-9-]{1,240}",ocid):
        raise ValueError("invalid OCID")
    notice=raw.get("id")
    url=notice_url(notice)
    key=release_identity("find-tender.service.gov.uk",raw)
    released=_timestamp(raw.get("date"))
    tags=raw.get("tag")
    if type(tags) is not list or not 1<=len(tags)<=16 or any(
            type(t) is not str or not re.fullmatch("[A-Za-z][A-Za-z0-9]{0,63}",t) for t in tags):
        raise ValueError("invalid release tags")
    if len(set(tags))!=len(tags):
        raise ValueError("duplicate release tag")
    tender=raw.get("tender")
    if tender is None:
        tender={}
    if type(tender) is not dict:
        raise ValueError("invalid tender section")
    reasons=[]
    if released>now:
        reasons.append("FUTURE_RELEASE")
    if not set(tags)<=TENDER_TAGS or raw.get("initiationType")!="tender":
        reasons.append("NOT_SUPPORTED_TENDER_EVENT")
    if tender.get("status")!="active":
        reasons.append("ACTIVE_STATUS_UNCONFIRMED")
    title=tender.get("title")
    if title is None or title=="":
        title="Notice "+notice+" (tender title unavailable)"
        reasons.append("TENDER_TITLE_UNVERIFIED")
    else:
        title=_text(title,512)
    period=tender.get("tenderPeriod")
    deadline=None
    try:
        if type(period) is not dict:
            raise ValueError("missing tender period")
        deadline=_timestamp(period.get("endDate"))
        if deadline<=now:
            reasons.append("REPORTED_DEADLINE_PASSED")
    except ValueError:
        reasons.append("REPORTED_DEADLINE_UNVERIFIED")
    # A release is an event, not a compiled process. Even active status is historical.
    blockers=reasons+["COMPLETE_PROCESS_HISTORY_UNVERIFIED","CURRENT_TENDER_STATE_UNVERIFIED",
        "REQUIREMENTS_UNVERIFIED","ELIGIBILITY_UNVERIFIED","DELIVERY_CAPABILITY_UNVERIFIED",
        "COMPENSATION_UNVERIFIED","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"]
    return dict(key=key,notice_id=notice,ocid=ocid,title=title,source_url=url,
        retrieved_at=now.isoformat(),release_date=released.isoformat(),tags=tags,
        deadline=deadline.isoformat() if deadline else None,
        research_candidate=not reasons,execution_eligible=False,external_authority=False,
        cash_exposure=None,blockers=blockers,
        todo=[dict(key=k,notice_id=notice,instruction=t,status="needs independent evidence")
              for k,t in CHECKS])

def _mark_latest(rows):
    groups={}
    for row in rows:
        groups.setdefault(row["ocid"],[]).append(row)
    for group in groups.values():
        latest=max(_timestamp(row["release_date"]) for row in group)
        newest=[row for row in group if _timestamp(row["release_date"])==latest]
        for row in group:
            reason=None
            if _timestamp(row["release_date"])<latest:
                reason="SUPERSEDED_WITHIN_COLLECTED_WINDOW"
            elif len(newest)>1:
                reason="AMBIGUOUS_LATEST_RELEASE"
            if reason:
                row["blockers"].append(reason)
                row["research_candidate"]=False

def search(query,*,approved=None,halt_check=None,transport=None,clock=None):
    def require_consent():
        decision=decide_fts_read(approved=approved,halted=halt_check() if callable(halt_check) else None)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require_consent()
    if type(query) is not FtsQuery:
        raise ValueError("validated FTS query required")
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    now=clock()
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware clock required")
    now=now.astimezone(timezone.utc)
    base=query.parameters(now)
    request=_request if transport is None else transport
    cursor=None
    seen_cursors=set()
    rows={}
    raw_by_key={}
    notice_keys={}
    digests=[]
    calls=0
    retried=False
    finished=False
    while calls<MAX_REQUESTS:
        if calls:
            sleep(1)
        require_consent()
        calls+=1
        params=dict(base)
        if cursor is not None:
            params["cursor"]=cursor
        try:
            status,raw=request(params)
        except Exception:
            raise SearchError("FTS_TRANSPORT_FAILURE") from None
        require_consent()
        if status==429:
            raise SearchError("FTS_RATE_LIMIT_STOP")
        if status in (500,502,503,504) and not retried and calls<MAX_REQUESTS:
            retried=True
            continue
        if status!=200:
            raise SearchError("FTS_HTTP_FAILURE")
        if type(raw) is not bytes or len(raw)>MAX_BYTES:
            raise SearchError("FTS_RESPONSE_TOO_LARGE_OR_INVALID")
        try:
            package=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
            if type(package) is not dict or package.get("version") not in ("1.1","1.1.5"):
                raise ValueError("unsupported release package version")
            releases=package.get("releases")
            if type(releases) is not list or len(releases)>PAGE_SIZE:
                raise ValueError("invalid release page")
            observed=clock()
            if type(observed) is not datetime or observed.utcoffset() is None:
                raise ValueError("invalid retrieval time")
            observed=observed.astimezone(timezone.utc)
            if observed<now:
                raise ValueError("clock moved backward")
            for item in releases:
                lead=_notice(item,observed)
                key=lead["key"]
                if lead["notice_id"] in notice_keys and notice_keys[lead["notice_id"]]!=key:
                    raise ValueError("ambiguous official notice identity")
                if key in raw_by_key:
                    if raw_by_key[key]!=item:
                        raise ValueError("conflicting release")
                    continue
                raw_by_key[key]=item
                notice_keys[lead["notice_id"]]=key
                rows[key]=lead
            cursor=_next_cursor(package,base)
            if cursor is not None:
                if cursor in seen_cursors or not releases:
                    raise ValueError("repeated or empty continuation")
                seen_cursors.add(cursor)
            digests.append(hashlib.sha256(raw).hexdigest())
        except (ValueError,TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
            raise SearchError("FTS_RESPONSE_INVALID_OR_INCONSISTENT") from None
        if cursor is None:
            finished=True
            break
    require_consent()
    if not digests:
        raise SearchError("FTS_NO_VALID_PAGE")
    leads=list(rows.values())
    _mark_latest(leads)
    if not finished:
        for lead in leads:
            lead["blockers"].append("COLLECTION_WINDOW_INCOMPLETE")
            lead["research_candidate"]=False
    leads.sort(key=lambda row:(not row["research_candidate"],row["deadline"] or "9999",row["notice_id"]))
    return dict(format=FORMAT,scope="Historical OCDS release research; current process not compiled",
        attribution="Contains public sector information licensed under the Open Government Licence v3.0.",
        source="UK Find a Tender",query=base,timezone_assumption="UTC for update-window strings",
        requests=calls,returned=len(leads),truncated=not finished,page_sha256=digests,leads=leads)
