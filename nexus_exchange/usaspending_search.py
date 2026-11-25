"""Public prime-award intelligence, never a solicitation or compensation offer."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import http.client
import json
import re
from time import sleep
from .governor import decide_usaspending_read
from .local_import import _pairs, _integer, _decimal, _constant
from .revenue_pathways import CHECKS
from .scout import _text, normalize
from .sam_search import SearchError

HOST="api.usaspending.gov"
PATH="/api/v2/search/spending_by_award/"
FORMAT="nexus-usaspending-research-v1"
MAX_REQUESTS=3
PAGE_SIZE=25
MAX_BYTES=2*1024*1024
FIELDS=("Award ID","Recipient Name","Recipient UEI","Awarding Agency",
        "Start Date","End Date","generated_internal_id")
CONTRACTOR_TASKS=(
    ("organization","Verify recipient's current legal entity, UEI and business capabilities."),
    ("demand","Find independent evidence of a current, authorized subcontract requirement."),
    ("permission","Check contract flow-down terms, subcontracting restrictions and outreach permission."),
    ("delivery","Confirm actual scope, staffing, delivery and applicable qualifications."),
    ("payment","Obtain written compensation, acceptance criteria and payment terms."),
    ("cost","Verify complete pre-payment cash exposure; award history is not revenue."),
    ("authorization","Obtain scoped owner approval before any external action."),
)

@dataclass(frozen=True,slots=True)
class SpendingQuery:
    naics: str
    start: date
    end: date

    def parameters(self,now,page=1):
        if type(self.naics) is not str or not re.fullmatch("[0-9]{6}",self.naics):
            raise ValueError("six-digit NAICS code required")
        if type(self.start) is not date or type(self.end) is not date:
            raise ValueError("date objects required")
        if not 0<=(self.end-self.start).days<=180 or self.end>now.date():
            raise ValueError("choose historical window up to 180 days")
        if type(page) is not int or not 1<=page<=MAX_REQUESTS:
            raise ValueError("invalid page")
        return dict(spending_level="awards",subawards=False,limit=PAGE_SIZE,page=page,
            filters={"award_type_codes":["A","B","C","D"],
                "naics_codes":{"require":[self.naics]},
                "recipient_type_names":["category_business"],
                "time_period":[{"start_date":self.start.isoformat(),
                    "end_date":self.end.isoformat(),"date_type":"date_signed"}]},
            fields=list(FIELDS),sort="Award ID",order="asc")

def award_url(identifier):
    if type(identifier) is not str or not re.fullmatch("CONT_AWD_[A-Za-z0-9_-]{1,240}",identifier):
        raise ValueError("invalid generated prime contract identifier")
    return "https://www.usaspending.gov/award/"+identifier

def _request(payload):
    # Fixed public POST search, not a mutation or award submission.
    connection=http.client.HTTPSConnection(HOST,443,timeout=10)
    try:
        body=json.dumps(payload,ensure_ascii=True,allow_nan=False).encode("ascii")
        connection.request("POST",PATH,body=body,headers={"Content-Type":"application/json",
            "Accept":"application/json","Accept-Encoding":"identity","User-Agent":"NexusExchange-Preview/1"})
        response=connection.getresponse()
        if response.status!=200:
            return response.status,b""
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise SearchError("USASPENDING_RESPONSE_TOO_LARGE")
        return response.status,raw
    except SearchError:
        raise
    except Exception:
        raise SearchError("USASPENDING_TRANSPORT_FAILURE") from None
    finally:
        connection.close()

def _date(value):
    if value is None or value=="":
        return None
    if type(value) is not str or not re.fullmatch("[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValueError("invalid date")
    return date.fromisoformat(value).isoformat()

def metadata(raw):
    if type(raw) is not dict:
        raise ValueError("invalid award metadata")
    recipient=_text(raw.get("recipient"),256)
    award_id=_text(raw.get("award_id"),128)
    agency=raw.get("agency")
    if agency is not None:
        agency=_text(agency,256)
    uei=raw.get("uei")
    if uei is not None and (type(uei) is not str or not re.fullmatch("[A-Z0-9]{12}",uei)):
        raise ValueError("invalid recipient UEI")
    start,end=_date(raw.get("performance_start")),_date(raw.get("performance_end"))
    if start and end and start>end:
        raise ValueError("inconsistent performance dates")
    return dict(recipient=recipient,award_id=award_id,agency=agency,uei=uei,
        performance_start=start,performance_end=end)

def _award(raw,now):
    if type(raw) is not dict:
        raise ValueError("invalid award")
    identifier=raw.get("generated_internal_id")
    url=award_url(identifier)
    internal=raw.get("internal_id")
    if type(internal) is not int or internal<1:
        raise ValueError("invalid internal ID")
    info=metadata(dict(recipient=raw.get("Recipient Name"),award_id=raw.get("Award ID"),
        agency=raw.get("Awarding Agency") or None,uei=raw.get("Recipient UEI") or None,
        performance_start=raw.get("Start Date"),performance_end=raw.get("End Date")))
    op=normalize(dict(source="usaspending",external_id=identifier,title=info["recipient"],
        source_url=url,retrieved_at=now.isoformat(),deadline=None,currency=None,amount=None))
    reasons=["HISTORICAL_AWARD_NOT_SOLICITATION","CURRENT_SUBCONTRACT_DEMAND_UNVERIFIED",
        "RECIPIENT_ENTITY_UNVERIFIED","SUBCONTRACT_PERMISSION_UNVERIFIED",
        "COMPENSATION_UNVERIFIED","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"]
    if info["uei"] is None:
        reasons.append("RECIPIENT_UEI_UNVERIFIED")
    if info["performance_end"] is None:
        reasons.append("PERFORMANCE_END_UNVERIFIED")
    elif info["performance_end"]<now.date().isoformat():
        reasons.append("REPORTED_PERFORMANCE_PERIOD_ENDED")
    return dict(key=op.key,notice_id=identifier,title=op.title,source_url=url,
        retrieved_at=now.isoformat(),deadline=None,award_metadata=info,
        research_candidate=False,execution_eligible=False,external_authority=False,
        cash_exposure=None,blockers=reasons,
        todo=[dict(key=k,notice_id=identifier,instruction=t,status="needs independent evidence")
              for k,t in CONTRACTOR_TASKS])

def search(query,*,approved=None,halt_check=None,transport=None,clock=None):
    def require_consent():
        decision=decide_usaspending_read(approved=approved,halted=halt_check() if callable(halt_check) else None)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require_consent()
    if type(query) is not SpendingQuery:
        raise ValueError("validated USAspending query required")
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    now=clock()
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware clock required")
    now=now.astimezone(timezone.utc)
    params=query.parameters(now)
    request=_request if transport is None else transport
    rows={}
    digests=[]
    calls=0
    page=1
    retried=False
    finished=False
    while calls<MAX_REQUESTS:
        if calls:
            sleep(1)
        require_consent()
        calls+=1
        try:
            status,raw=request(query.parameters(now,page))
        except Exception:
            raise SearchError("USASPENDING_TRANSPORT_FAILURE") from None
        require_consent()
        if status==429:
            raise SearchError("USASPENDING_RATE_LIMIT_STOP")
        if status in (500,502,503,504) and not retried and calls<MAX_REQUESTS:
            retried=True
            continue
        if status!=200:
            raise SearchError("USASPENDING_HTTP_FAILURE")
        if type(raw) is not bytes or len(raw)>MAX_BYTES:
            raise SearchError("USASPENDING_RESPONSE_TOO_LARGE_OR_INVALID")
        try:
            data=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
            if type(data) is not dict or data.get("spending_level")!="awards" or type(data.get("limit")) is not int or data["limit"]!=PAGE_SIZE:
                raise ValueError("unexpected award response")
            records=data.get("results")
            meta=data.get("page_metadata")
            if type(records) is not list or len(records)>PAGE_SIZE or type(meta) is not dict:
                raise ValueError("invalid award page")
            if type(meta.get("page")) is not int or meta["page"]!=page or type(meta.get("hasNext")) is not bool:
                raise ValueError("invalid page metadata")
            if meta["hasNext"] and len(records)!=PAGE_SIZE:
                raise ValueError("incomplete page")
            observed=clock()
            if type(observed) is not datetime or observed.utcoffset() is None:
                raise ValueError("invalid retrieval time")
            observed=observed.astimezone(timezone.utc)
            if observed<now:
                raise ValueError("clock moved backward")
            for record in records:
                lead=_award(record,observed)
                if lead["notice_id"] in rows:
                    raise ValueError("duplicate award across pages")
                rows[lead["notice_id"]]=lead
            digests.append(hashlib.sha256(raw).hexdigest())
        except (ValueError,TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
            raise SearchError("USASPENDING_RESPONSE_INVALID_OR_INCONSISTENT") from None
        if not meta["hasNext"]:
            finished=True
            break
        page+=1
    require_consent()
    if not digests:
        raise SearchError("USASPENDING_NO_VALID_PAGE")
    leads=sorted(rows.values(),key=lambda row:(row["title"].casefold(),row["notice_id"]))
    return dict(format=FORMAT,scope="Historical prime contract intelligence only; no open work or execution eligibility",
        source="USAspending.gov",query=params,requests=calls,returned=len(leads),
        truncated=not finished,page_sha256=digests,leads=leads)
