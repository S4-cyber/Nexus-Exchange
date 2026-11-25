"""One bounded Contracts Finder OCDS release page; not a current state compiler."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import http.client
import json
import re
from threading import Lock
from time import monotonic_ns
from urllib.parse import urlencode

from .governor import decide_cf_read
from .local_import import _pairs, _integer, _decimal, _constant
from .ocds_identity import release_identity
from .revenue_pathways import CHECKS
from .sam_search import SearchError
from .scout import _text, _timestamp

HOST="www.contractsfinder.service.gov.uk"
PATH="/Published/Notices/OCDS/Search"
FORMAT="nexus-cf-research-v1"
PAGE_SIZE=50
MAX_BYTES=4*1024*1024
_UUID=r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_TENDER_TAGS=frozenset(("tender","tenderUpdate","tenderAmendment"))
_LOCK=Lock()
_NEXT_REQUEST_NS=0


def _utc(value):
    if type(value) is not datetime or value.utcoffset() is None:
        raise ValueError("aware timestamps required")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True,slots=True)
class CfQuery:
    published_from: datetime
    published_to: datetime
    cpv_prefix: str

    def parameters(self,now):
        start,end,now=map(_utc,(self.published_from,self.published_to,now))
        if (not timedelta(0)<end-start<=timedelta(days=1) or end>now
                or start.microsecond or end.microsecond):
            raise ValueError("bounded historical publication window, whole seconds required")
        if type(self.cpv_prefix) is not str or not re.fullmatch(r"[0-9]{2,8}",self.cpv_prefix):
            raise ValueError("CPV prefix must contain 2–8 ASCII digits")
        # All stages, including awards and cancellations: never discard contrary
        # events before local selection. CPV is a local filter, not transmitted.
        return dict(publishedFrom=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    publishedTo=end.strftime("%Y-%m-%dT%H:%M:%SZ"),limit=str(PAGE_SIZE))


def _notice_id(value):
    if type(value) is not str or not re.fullmatch(_UUID+r"-[1-9][0-9]{0,11}",value):
        raise ValueError("invalid Contracts Finder release identity")
    return value.rsplit("-",1)[0]


def notice_url(release_id):
    return "https://"+HOST+"/Notice/"+_notice_id(release_id)


def _codes(tender):
    primary=tender.get("classification")
    other=tender.get("additionalClassifications",[])
    if type(other) is not list or len(other)>99:
        raise ValueError("invalid classification list")
    codes=set()
    for item in ([] if primary is None else [primary])+other:
        if type(item) is not dict:
            raise ValueError("invalid classification")
        if item.get("scheme")!="CPV":
            continue
        code=item.get("id")
        if type(code) is not str or not re.fullmatch(r"[0-9]{8}",code):
            raise ValueError("invalid CPV")
        codes.add(code)
    return [dict(scheme="CPV",code=code) for code in sorted(codes)]


def _notice(raw,query,now):
    if type(raw) is not dict:
        raise ValueError("invalid release")
    rid=raw.get("id")
    url=notice_url(rid)
    ocid=raw.get("ocid")
    if type(ocid) is not str or not re.fullmatch("ocds-b5fd17-"+_UUID,ocid):
        raise ValueError("invalid Contracts Finder OCID")
    published=_timestamp(raw.get("date"))
    tags=raw.get("tag")
    if (type(tags) is not list or not 1<=len(tags)<=16
            or any(type(tag) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}",tag) for tag in tags)
            or len(set(tags))!=len(tags)):
        raise ValueError("invalid release tags")
    tender=raw.get("tender",{})
    if type(tender) is not dict:
        raise ValueError("invalid tender")
    reasons=[]
    if not _utc(query.published_from)<=published<=_utc(query.published_to) or published>now:
        reasons.append("PUBLICATION_OUTSIDE_WINDOW")
    if not set(tags)<=_TENDER_TAGS or raw.get("initiationType")!="tender":
        reasons.append("NOT_SUPPORTED_TENDER_EVENT")
    if tender.get("status")!="active":
        reasons.append("ACTIVE_STATUS_UNCONFIRMED")
    if raw.get("awards") or raw.get("contracts"):
        reasons.append("AWARD_OR_CONTRACT_EVENT_PRESENT")
    title=tender.get("title")
    if title is None or title=="":
        title="Release "+rid+" (title unavailable)"
        reasons.append("TENDER_TITLE_UNVERIFIED")
    else:
        title=_text(title,512)
    codes=_codes(tender)
    if not codes:
        reasons.append("CPV_CLASSIFICATION_UNVERIFIED")
    elif not any(item["code"].startswith(query.cpv_prefix) for item in codes):
        reasons.append("REQUESTED_CPV_PREFIX_NOT_REPORTED")
    deadline=None
    try:
        period=tender.get("tenderPeriod")
        if type(period) is not dict:
            raise ValueError("missing tender period")
        deadline=_timestamp(period.get("endDate"))
        if deadline<=now:
            reasons.append("REPORTED_DEADLINE_PASSED")
    except ValueError:
        reasons.append("REPORTED_DEADLINE_UNVERIFIED")
    return dict(key=release_identity("contractsfinder.service.gov.uk",raw),
                notice_id=rid,ocid=ocid,title=title,source_url=url,
                retrieved_at=now.isoformat(),release_date=published.isoformat(),
                tags=tags,reported_codes=codes,deadline=deadline.isoformat() if deadline else None,
                research_candidate=not reasons,execution_eligible=False,external_authority=False,
                cash_exposure=None,blockers=reasons+["COMPLETE_PROCESS_HISTORY_UNVERIFIED",
                    "CURRENT_TENDER_STATE_UNVERIFIED","REQUIREMENTS_UNVERIFIED",
                    "ELIGIBILITY_UNVERIFIED","DELIVERY_CAPABILITY_UNVERIFIED",
                    "COMPENSATION_UNVERIFIED","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"],
                todo=[dict(key=k,notice_id=rid,instruction=t,status="needs independent evidence")
                      for k,t in CHECKS])


def _mark_latest(rows):
    groups={}
    for row in rows:
        groups.setdefault(row["ocid"],[]).append(row)
    for group in groups.values():
        latest=max(_timestamp(row["release_date"]) for row in group)
        ties=sum(_timestamp(row["release_date"])==latest for row in group)
        for row in group:
            reason=("SUPERSEDED_WITHIN_COLLECTED_WINDOW" if _timestamp(row["release_date"])<latest
                    else "AMBIGUOUS_LATEST_RELEASE" if ties>1 else None)
            if reason:
                row["research_candidate"]=False
                row["blockers"].append(reason)


def _request(params):
    """Fixed one-page GET, process-local spacing and conservative throttle cooldown."""
    global _NEXT_REQUEST_NS
    if not _LOCK.acquire(blocking=False):
        raise SearchError("CF_LOCAL_REQUEST_BUSY")
    connection=None
    try:
        tick=monotonic_ns()
        if tick<_NEXT_REQUEST_NS:
            raise SearchError("CF_LOCAL_COOLDOWN")
        _NEXT_REQUEST_NS=tick+3_100_000_000
        connection=http.client.HTTPSConnection(HOST,443,timeout=10)
        connection.request("GET",PATH+"?"+urlencode(params),headers={
            "Accept":"application/json","Accept-Encoding":"identity","User-Agent":"NexusExchange-Preview/1"})
        response=connection.getresponse()
        if response.status in (403,429,503):
            _NEXT_REQUEST_NS=max(_NEXT_REQUEST_NS,monotonic_ns()+300_000_000_000)
        if response.status!=200:
            return response.status,b""
        media=response.getheader("Content-Type","").split(";",1)[0].strip().lower()
        if media!="application/json" or response.getheader("Content-Encoding","identity").lower()!="identity":
            raise SearchError("CF_RESPONSE_MEDIA")
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise SearchError("CF_RESPONSE_TOO_LARGE")
        return response.status,raw
    except SearchError:
        raise
    except Exception:
        raise SearchError("CF_TRANSPORT_FAILURE") from None
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            _LOCK.release()


def search(query,*,approved=None,halt_check=None,transport=None,clock=None):
    def require():
        decision=decide_cf_read(approved=approved,halted=halt_check() if callable(halt_check) else None)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require()
    if type(query) is not CfQuery:
        raise ValueError("validated Contracts Finder query required")
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    start=_utc(clock())
    params=query.parameters(start)
    require()
    request=_request if transport is None else transport
    try:
        status,raw=request(params)
    except SearchError:
        raise
    except Exception:
        raise SearchError("CF_TRANSPORT_FAILURE") from None
    require()
    if type(status) is not int or status!=200:
        raise SearchError("CF_ACCESS_OR_RATE_LIMIT_STOP" if status in (403,429,503) else "CF_HTTP_FAILURE")
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BYTES:
        raise SearchError("CF_RESPONSE_TOO_LARGE_OR_INVALID")
    try:
        package=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                           parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
        if type(package) is not dict or package.get("version") not in ("1.1","1.1.5"):
            raise ValueError("unsupported release package")
        releases=package.get("releases")
        if type(releases) is not list or len(releases)>PAGE_SIZE:
            raise ValueError("invalid release page")
        links=package.get("links",{})
        if type(links) is not dict:
            raise ValueError("invalid link metadata")
        next_link=links.get("next")
        if next_link is not None and (type(next_link) is not str or len(next_link)>4096):
            raise ValueError("invalid continuation marker")
        # Never follow source-controlled links. A full page without an explicit
        # continuation is conservatively treated as possibly incomplete too.
        truncated=bool(next_link) or len(releases)==PAGE_SIZE
        now=_utc(clock())
        if now<start:
            raise ValueError("clock moved backward")
        rows=[]
        seen={}
        for release in releases:
            lead=_notice(release,query,now)
            rid=lead["notice_id"]
            if rid in seen:
                if seen[rid]!=release:
                    raise ValueError("conflicting release identity")
                continue
            seen[rid]=release
            rows.append(lead)
        _mark_latest(rows)
        if truncated:
            for row in rows:
                row["research_candidate"]=False
                row["blockers"].append("COLLECTION_WINDOW_INCOMPLETE")
        rows.sort(key=lambda row:(not row["research_candidate"],row["deadline"] or "9999",row["notice_id"]))
    except (ValueError,TypeError,KeyError,ArithmeticError,UnicodeError,RecursionError):
        raise SearchError("CF_RESPONSE_INVALID_OR_INCONSISTENT") from None
    require()
    return dict(format=FORMAT,source="UK Contracts Finder",
        scope="One historical OCDS release page; current process not compiled",
        attribution="Contains public sector information licensed under the Open Government Licence v3.0. Source: Cabinet Office / Contracts Finder.",
        query=params,local_cpv_prefix=query.cpv_prefix,requests=1,returned=len(rows),
        truncated=truncated,page_sha256=[sha256(raw).hexdigest()],leads=rows)
