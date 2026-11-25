"""Owner-consented, keyless TED v3 search; research only, no dispatch."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import http.client
import json
import re
from time import sleep
from .local_import import _pairs, _integer, _decimal, _constant
from .revenue_pathways import CHECKS
from .scout import _text, normalize
from .sam_search import SearchError

HOST = "api.ted.europa.eu"
PATH = "/v3/notices/search"
FORMAT = "nexus-ted-research-v1"
PAGE_SIZE = 25
MAX_REQUESTS = 3
MAX_BYTES = 2 * 1024 * 1024
OPEN_TYPES = ("cn-standard", "cn-social")
FIELDS = ("publication-number", "publication-date", "notice-title", "form-type",
          "notice-type", "classification-cpv", "deadline-receipt-tender-date-lot")

@dataclass(frozen=True, slots=True)
class TedQuery:
    cpv_prefix: str
    published_from: date
    published_to: date

    def parameters(self, now, page=1):
        if type(self.cpv_prefix) is not str or not re.fullmatch("[0-9]{2,8}",self.cpv_prefix):
            raise ValueError("CPV prefix must contain 2–8 ASCII digits")
        if type(self.published_from) is not date or type(self.published_to) is not date:
            raise ValueError("date objects required")
        if not 0 <= (self.published_to-self.published_from).days <= 31 or self.published_to>now.date():
            raise ValueError("invalid publication window")
        if type(page) is not int or not 1<=page<=MAX_REQUESTS:
            raise ValueError("invalid page")
        prefix=self.cpv_prefix+("*" if len(self.cpv_prefix)<8 else "")
        query=("classification-cpv="+prefix+
               " AND publication-date>="+self.published_from.strftime("%Y%m%d")+
               " AND publication-date<="+self.published_to.strftime("%Y%m%d")+
               " AND notice-type IN (cn-standard cn-social) SORT BY publication-date DESC")
        return dict(query=query,fields=list(FIELDS),page=page,limit=PAGE_SIZE,
                    scope="ACTIVE",paginationMode="PAGE_NUMBER",onlyLatestVersions=True)

def notice_url(number):
    if type(number) is not str or not re.fullmatch("[0-9]{1,8}-[0-9]{4}",number):
        raise ValueError("invalid publication number")
    seq,year=number.split("-")
    if not int(seq) or not 1900<=int(year)<=9999:
        raise ValueError("invalid publication number")
    return "https://ted.europa.eu/en/notice/-/detail/"+number

def _request(payload):
    # POST is restricted to the published-notice SEARCH endpoint.
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
            raise SearchError("TED_RESPONSE_TOO_LARGE")
        return response.status,raw
    except SearchError:
        raise
    except Exception:
        raise SearchError("TED_TRANSPORT_FAILURE") from None
    finally:
        connection.close()

def _strings(value,limit=100):
    if type(value) is str:
        value=[value]
    if type(value) is not list or not 1<=len(value)<=limit:
        raise ValueError("invalid bounded field list")
    return [_text(v,512) for v in value]

def _title(value):
    if type(value) is str:
        return _text(value,512),None
    if type(value) is not dict or not 1<=len(value)<=40:
        raise ValueError("invalid multilingual title")
    if any(type(k) is not str or not re.fullmatch("[a-zA-Z]{2,3}",k) for k in value):
        raise ValueError("invalid language")
    language="eng" if "eng" in value else sorted(value)[0]
    return _strings(value[language],20)[0],language

def _calendar(value):
    # Never invent a time of day or join unassociated lot dates and times.
    if type(value) is not str or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])?",value):
        raise ValueError("invalid calendar date")
    return date.fromisoformat(value[:10])

def _notice(raw,query,now):
    if type(raw) is not dict:
        raise ValueError("invalid notice")
    number=raw.get("publication-number")
    url=notice_url(number)
    seq,year=number.split("-")
    title,language=_title(raw.get("notice-title"))
    reasons=[]
    kind=raw.get("notice-type")
    if raw.get("form-type")!="competition" or kind not in OPEN_TYPES:
        reasons.append("NOT_SUPPORTED_COMPETITION")
    try:
        published=_calendar(raw.get("publication-date"))
        if not query.published_from<=published<=query.published_to:
            reasons.append("PUBLICATION_OUTSIDE_WINDOW")
    except ValueError:
        published=None
        reasons.append("PUBLICATION_DATE_UNVERIFIED")
    try:
        cpvs=_strings(raw.get("classification-cpv"))
        if not all(re.fullmatch("[0-9]{8}",cpv) for cpv in cpvs):
            raise ValueError("invalid CPV")
        if not any(cpv.startswith(query.cpv_prefix) for cpv in cpvs):
            reasons.append("CLASSIFICATION_MISMATCH")
    except ValueError:
        cpvs=[]
        reasons.append("CLASSIFICATION_UNVERIFIED")
    try:
        dates=_strings(raw.get("deadline-receipt-tender-date-lot"))
        parsed=[_calendar(value) for value in dates]
        if min(parsed)<=now.date():
            reasons.append("DEADLINE_DATE_PASSED_OR_TODAY")
    except ValueError:
        dates=[]
        parsed=[]
        reasons.append("DEADLINE_DATE_UNVERIFIED")
    op=normalize(dict(source="ted.europa.eu",external_id=str(int(seq))+"-"+year,title=title,
        source_url=url,retrieved_at=now.isoformat(),deadline=None,currency=None,amount=None))
    blockers=reasons+["EXACT_LOT_DEADLINE_UNVERIFIED","CURRENT_NOTICE_VERSION_UNVERIFIED",
        "REQUIREMENTS_UNVERIFIED","ELIGIBILITY_UNVERIFIED","DELIVERY_CAPABILITY_UNVERIFIED",
        "COMPENSATION_UNVERIFIED","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"]
    return dict(key=op.key,notice_id=number,title=title,source_url=url,
        retrieved_at=now.isoformat(),publication_date=published.isoformat() if published else None,
        deadline=None,deadline_dates=dates,earliest_deadline_date=min(parsed).isoformat() if parsed else None,
        title_language=language,notice_type=kind if type(kind) is str and kind in OPEN_TYPES else None,
        classifications=cpvs,research_candidate=not reasons,execution_eligible=False,
        external_authority=False,cash_exposure=None,blockers=blockers,
        todo=[dict(key=k,notice_id=number,instruction=t,status="needs independent evidence") for k,t in CHECKS])

def search(query,*,approved=None,halt_check=None,transport=None,clock=None):
    from .governor import decide_ted_read
    def require_consent():
        decision=decide_ted_read(approved=approved,halted=halt_check() if callable(halt_check) else None)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require_consent()
    if type(query) is not TedQuery:
        raise ValueError("validated TED query required")
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    now=clock()
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware clock required")
    now=now.astimezone(timezone.utc)
    params=query.parameters(now)
    request=_request if transport is None else transport
    rows={}
    total=None
    calls=0
    page=1
    retried=False
    digests=[]
    while calls<MAX_REQUESTS:
        if calls:
            sleep(1)
        require_consent()
        calls+=1
        try:
            status,raw=request(query.parameters(now,page))
        except Exception:
            raise SearchError("TED_TRANSPORT_FAILURE") from None
        require_consent()
        if status==429:
            raise SearchError("TED_RATE_LIMIT_STOP")
        if status in (500,502,503,504) and not retried and calls<MAX_REQUESTS:
            retried=True
            continue
        if status!=200:
            raise SearchError("TED_HTTP_FAILURE")
        if type(raw) is not bytes or len(raw)>MAX_BYTES:
            raise SearchError("TED_RESPONSE_TOO_LARGE_OR_INVALID")
        try:
            data=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
            if type(data) is not dict or data.get("timedOut",False) is not False:
                raise ValueError("incomplete response")
            count=data.get("totalNoticeCount")
            records=data.get("notices")
            if type(count) is not int or count<0 or (total is not None and total!=count):
                raise ValueError("inconsistent total")
            if type(records) is not list or len(records)!=min(PAGE_SIZE,max(0,count-(page-1)*PAGE_SIZE)):
                raise ValueError("incomplete page")
            observed=clock()
            if type(observed) is not datetime or observed.utcoffset() is None:
                raise ValueError("invalid retrieval time")
            observed=observed.astimezone(timezone.utc)
            if observed<now:
                raise ValueError("clock moved backward")
            for raw_notice in records:
                lead=_notice(raw_notice,query,observed)
                if lead["key"] in rows:
                    raise ValueError("duplicate notice")
                rows[lead["key"]]=lead
            total=count
            digests.append(hashlib.sha256(raw).hexdigest())
        except (ValueError,TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
            raise SearchError("TED_RESPONSE_INVALID_OR_INCONSISTENT") from None
        if page*PAGE_SIZE>=total:
            break
        page+=1
    require_consent()
    if total is None:
        raise SearchError("TED_NO_VALID_PAGE")
    leads=sorted(rows.values(),key=lambda x:(not x["research_candidate"],
        x["earliest_deadline_date"] or "9999",x["notice_id"]))
    return dict(format=FORMAT,scope="Public notice research only; no execution eligibility",
        attribution="Source: TED - Tenders Electronic Daily, European Union, https://ted.europa.eu",
        query=params,requests=calls,reported_total=total,returned=len(leads),
        truncated=len(leads)<total,page_sha256=digests,leads=leads)
