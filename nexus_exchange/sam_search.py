"""User-consented, fixed-origin read-only SAM.gov search; no commercial dispatch."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import http.client
import json
import re
from urllib.parse import urlencode
from .governor import decide_sam_read
from .local_import import _pairs, _integer, _decimal, _constant
from .scout import _text, _timestamp, normalize

HOST = "api.sam.gov"
PATH = "/opportunities/v2/search"
MAX_REQUESTS = 3
PAGE_SIZE = 25
MAX_BYTES = 2 * 1024 * 1024
OPEN_TYPES = {"Solicitation", "Combined Synopsis/Solicitation"}

class SearchError(RuntimeError):
    """Sanitized provider failure, without URL, response text or credentials."""

@dataclass(frozen=True, slots=True)
class Query:
    posted_from: date
    posted_to: date
    title: str
    procurement_type: str = "k"

    def parameters(self, now):
        if type(self.posted_from) is not date or type(self.posted_to) is not date:
            raise ValueError("date objects required")
        if not 0 <= (self.posted_to-self.posted_from).days <= 31 or self.posted_to > now.date():
            raise ValueError("choose a past or current date window of at most 31 days")
        if type(self.procurement_type) is not str or self.procurement_type not in ("o","k"):
            raise ValueError("choose solicitation or combined synopsis/solicitation")
        return dict(postedFrom=self.posted_from.strftime("%m/%d/%Y"),
            postedTo=self.posted_to.strftime("%m/%d/%Y"),title=_text(self.title,120),
            ptype=self.procurement_type,limit=PAGE_SIZE)

def _request(params, api_key):
    """Only fixed HTTPS host/path; no redirects, arbitrary URLs or response logging."""
    connection = http.client.HTTPSConnection(HOST,443,timeout=10)
    try:
        query = urlencode(dict(params,api_key=api_key))
        connection.request("GET",PATH+"?"+query,headers={"Accept":"application/json",
            "Accept-Encoding":"identity","User-Agent":"NexusExchange-Preview/1"})
        response = connection.getresponse()
        if response.status != 200:
            return response.status,b""
        raw = response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise SearchError("SAM_RESPONSE_TOO_LARGE")
        return response.status,raw
    except SearchError:
        raise
    except Exception:
        raise SearchError("SAM_TRANSPORT_FAILURE") from None
    finally:
        connection.close()

def _notice(raw, now):
    if type(raw) is not dict:
        raise ValueError("invalid notice")
    notice = raw.get("noticeId")
    if type(notice) is not str or not re.fullmatch("[0-9a-fA-F]{32}",notice):
        raise ValueError("invalid notice ID")
    notice = notice.lower()
    title = _text(raw.get("title"),512)
    kind = _text(raw.get("type"),100)
    reasons = []
    if kind not in OPEN_TYPES:
        reasons.append("NOT_SOLICITATION")
    if raw.get("active") != "Yes":
        reasons.append("ACTIVE_STATUS_UNCONFIRMED")
    posted = raw.get("postedDate")
    try:
        if type(posted) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?",posted):
            raise ValueError("invalid posted date")
        posted_date = date.fromisoformat(posted[:10])
        if posted_date > now.date():
            reasons.append("FUTURE_POSTED_DATE")
    except ValueError:
        posted_date = None
        reasons.append("POSTED_DATE_UNVERIFIED")
    deadline = None
    try:
        deadline = _timestamp(raw.get("responseDeadLine"))
        if deadline<=now:
            reasons.append("DEADLINE_PASSED")
    except ValueError:
        reasons.append("DEADLINE_UNVERIFIED")
    source_url = "https://sam.gov/opp/"+notice+"/view"
    opportunity = normalize(dict(source="sam.gov",external_id=notice,title=title,
        source_url=source_url,retrieved_at=now.isoformat(),
        deadline=deadline.isoformat() if deadline else None,currency=None,amount=None))
    # Retain selected public metadata only, not contact details or arbitrary links.
    info = {}
    for field in ("solicitationNumber","fullParentPathName","naicsCode","classificationCode",
                  "typeOfSetAside","typeOfSetAsideDescription"):
        value = raw.get(field)
        if value is not None:
            info[field] = _text(value,512)
    research_candidate = not reasons
    blockers = reasons+["REQUIREMENTS_UNVERIFIED","ELIGIBILITY_UNVERIFIED",
        "DELIVERY_CAPABILITY_UNVERIFIED","COMPENSATION_UNVERIFIED",
        "CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"]
    return dict(key=opportunity.key,notice_id=notice,title=title,source_url=source_url,
        retrieved_at=now.isoformat(),posted_date=posted_date.isoformat() if posted_date else None,
        deadline=deadline.isoformat() if deadline else None,notice_type=kind,metadata=info,
        research_candidate=research_candidate,execution_eligible=False,external_authority=False,
        cash_exposure=None,blockers=blockers)

def search(query, api_key, *, approved=None, halt_check=None, transport=None, clock=None):
    """One owner-initiated search, at most three requests, never auto-executes."""
    def require_consent():
        halted = halt_check() if callable(halt_check) else None
        decision = decide_sam_read(approved=approved,halted=halted)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require_consent()
    if type(query) is not Query:
        raise ValueError("validated SAM query required")
    if type(api_key) is not str or not re.fullmatch("[A-Za-z0-9_-]{8,256}",api_key):
        raise ValueError("invalid API key format")
    clock = clock if clock is not None else lambda:datetime.now(timezone.utc)
    now = clock()
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware clock required")
    now = now.astimezone(timezone.utc)
    params=query.parameters(now)
    # No secret in serialized query/report, including accidental entry in title.
    if api_key in params["title"]:
        raise ValueError("search text contains credential")
    request = _request if transport is None else transport
    records={}
    total=None
    offset=0
    calls=0
    retried=False
    page_digests=[]
    while calls<MAX_REQUESTS:
        require_consent()
        calls+=1
        try:
            status,raw=request(dict(params,offset=offset),api_key)
        except Exception:
            raise SearchError("SAM_TRANSPORT_FAILURE") from None
        require_consent()
        if status==429:
            raise SearchError("SAM_RATE_LIMIT_STOP")
        if status in (500,502,503,504) and not retried and calls<MAX_REQUESTS:
            retried=True
            continue
        if status!=200:
            raise SearchError("SAM_HTTP_FAILURE_"+str(status) if type(status) is int and 100<=status<=599 else "SAM_HTTP_FAILURE")
        if type(raw) is not bytes or len(raw)>MAX_BYTES:
            raise SearchError("SAM_RESPONSE_TOO_LARGE_OR_INVALID")
        if api_key.encode() in raw:
            raise SearchError("SAM_RESPONSE_CONTAINS_CREDENTIAL")
        try:
            data=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
            if type(data) is not dict:
                raise ValueError("invalid response")
            count=data.get("totalRecords")
            page=data.get("opportunitiesData")
            if type(count) is not int or count<0 or (total is not None and count!=total):
                raise ValueError("changing record total")
            if type(data.get("offset")) is not int or data["offset"]!=offset or type(data.get("limit")) is not int or data["limit"]!=PAGE_SIZE:
                raise ValueError("unexpected pagination metadata")
            if count==0 and page is None:
                page=[]
            if type(page) is not list or len(page)!=min(PAGE_SIZE,max(0,count-offset*PAGE_SIZE)):
                raise ValueError("incomplete page")
            observed=clock()
            if type(observed) is not datetime or observed.utcoffset() is None:
                raise ValueError("invalid retrieval time")
            observed=observed.astimezone(timezone.utc)
            if observed<now:
                raise ValueError("clock moved backward")
            for item in page:
                lead=_notice(item,observed)
                if lead["notice_id"] in records:
                    raise ValueError("duplicate notice across pages")
                records[lead["notice_id"]]=lead
            total=count
            page_digests.append(hashlib.sha256(raw).hexdigest())
        except (ValueError,TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
            raise SearchError("SAM_RESPONSE_INVALID_OR_INCONSISTENT") from None
        offset+=1
        if offset*PAGE_SIZE>=total:
            break
    require_consent()
    if total is None:
        raise SearchError("SAM_NO_VALID_PAGE")
    leads=sorted(records.values(),key=lambda x:(not x["research_candidate"],
        x["deadline"] or "9999",x["notice_id"]))
    report=dict(format="nexus-sam-research-v1",scope="Read-only notice discovery; no execution eligibility",
        query=params,requests=calls,reported_total=total,returned=len(leads),
        truncated=len(leads)<total,page_sha256=page_digests,leads=leads)
    if api_key in json.dumps(report,ensure_ascii=True):
        raise SearchError("SAM_REPORT_CONTAINS_CREDENTIAL")
    return report
