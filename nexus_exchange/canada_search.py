"""Bounded, keyless CanadaBuys open tender CSV discovery, research only."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import csv
import hashlib
from .public_feeds import read_feed
import io
import re
from threading import Lock
from .governor import decide_canada_read
from .revenue_pathways import CHECKS
from .sam_search import SearchError
from .scout import _text, _timestamp, normalize

HOST = "canadabuys.canada.ca"
PATH = "/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"
DATA_URL = "https://"+HOST+PATH
FORMAT = "nexus-canada-research-v1"
MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 20000
MAX_RESULTS = 75
MAX_FIELD = 1024 * 1024
MAX_AGE = timedelta(hours=48)
CSV_LOCK = Lock()
REFERENCE = "referenceNumber-numeroReference"
TITLE = "title-titre-eng"
FRENCH_TITLE = "title-titre-fra"
PUBLICATION = "publicationDate-datePublication"
CLOSING = "tenderClosingDate-appelOffresDateCloture"
NOTICE_TYPE = "noticeType-avisType-eng"
STATUS_FIELDS = ("tenderStatus-appelOffresStatut-eng","tenderStatus-tenderStatut-eng")
REQUIRED = frozenset({REFERENCE,TITLE,PUBLICATION,CLOSING,NOTICE_TYPE})
OPEN_TYPES = frozenset({"request for proposal","request for quotation","invitation to tender",
    "request for tender","notice of proposed procurement","request for standing offer",
    "request for supply arrangement"})

@dataclass(frozen=True, slots=True)
class CanadaQuery:
    keyword: str

    def validated(self):
        keyword=_text(self.keyword,120)
        if len(keyword)<3:
            raise ValueError("keyword must contain at least three characters")
        return keyword.casefold()

def notice_url(reference):
    if type(reference) is not str or not re.fullmatch(r"(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,127}|SSC-[0-9]{2}-[0-9]{8}:T)",reference):
        raise ValueError("invalid CanadaBuys reference")
    if reference.startswith(("MX-","cb-","WS")):
        return "https://"+HOST+"/en/tender-opportunities/tender-notice/"+reference
    # Legacy identifiers may not resolve to detail pages; do not guess.
    return "https://"+HOST+"/en/tender-opportunities"

def _request():
    try:
        return read_feed("canada")
    except Exception:
        raise SearchError("CANADA_TRANSPORT_FAILURE") from None


def _dataset_time(header,now):
    try:
        if type(header) is not str or len(header)>128:
            raise ValueError("missing modification time")
        parsed=parsedate_to_datetime(header)
        if parsed.utcoffset() is None:
            raise ValueError("missing offset")
        stamp=parsed.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):
        return None,"DATASET_FRESHNESS_UNVERIFIED"
    if stamp>now:
        return stamp,"DATASET_TIMESTAMP_IN_FUTURE"
    if now-stamp>MAX_AGE:
        return stamp,"DATASET_STALE"
    return stamp,None

def _publication(value):
    if not re.fullmatch("[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValueError("invalid publication date")
    return date.fromisoformat(value)

def _closing(value):
    # Preserve timezone-less local dates and times; do not assume UTC.
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",value):
        return datetime.fromisoformat(value),None
    stamp=_timestamp(value)
    return stamp,stamp

def _lead(row,status_field,now,freshness):
    reference=row[REFERENCE]
    url=notice_url(reference)
    english=row[TITLE].strip()
    title=_text(english or row.get(FRENCH_TITLE,""),512)
    kind=_text(row[NOTICE_TYPE],120)
    status=_text(row[status_field],80)
    reasons=[]
    if status.casefold()!="open":
        reasons.append("NOT_OPEN")
    if kind.casefold() not in OPEN_TYPES:
        reasons.append("NOTICE_TYPE_REQUIRES_REVIEW")
    try:
        published=_publication(row[PUBLICATION])
        if published>now.date():
            reasons.append("FUTURE_PUBLICATION")
    except ValueError:
        published=None
        reasons.append("PUBLICATION_DATE_UNVERIFIED")
    exact=None
    reported=None
    earliest=None
    try:
        reported,exact=_closing(row[CLOSING])
        earliest=reported.date().isoformat()
        if (exact is not None and exact<=now) or (exact is None and reported.date()<=now.date()):
            reasons.append("REPORTED_DEADLINE_PASSED_OR_TODAY")
    except ValueError:
        reasons.append("REPORTED_DEADLINE_UNVERIFIED")
    if freshness:
        reasons.append(freshness)
    op=normalize(dict(source=HOST,external_id=reference,title=title,source_url=url,
        retrieved_at=now.isoformat(),deadline=exact.isoformat() if exact else None,
        currency=None,amount=None))
    blockers=reasons+["CURRENT_NOTICE_STATE_UNVERIFIED","REQUIREMENTS_UNVERIFIED",
        "ELIGIBILITY_UNVERIFIED","DELIVERY_CAPABILITY_UNVERIFIED",
        "COMPENSATION_UNVERIFIED","CASH_EXPOSURE_UNKNOWN","OWNER_APPROVAL_REQUIRED"]
    if exact is None:
        blockers.append("EXACT_DEADLINE_TIMEZONE_UNVERIFIED")
    if url.endswith("/tender-opportunities"):
        blockers.append("DIRECT_NOTICE_LINK_UNVERIFIED")
    return dict(key=op.key,notice_id=reference,title=title,title_language="eng" if english else "fra",
        source_url=url,retrieved_at=now.isoformat(),publication_date=published.isoformat() if published else None,
        deadline=exact.isoformat() if exact else None,
        reported_closing=reported.isoformat() if reported else None,earliest_deadline_date=earliest,
        notice_type=kind,status=status,research_candidate=not reasons,execution_eligible=False,
        external_authority=False,cash_exposure=None,blockers=blockers,
        todo=[dict(key=k,notice_id=reference,instruction=t,status="needs independent evidence") for k,t in CHECKS])

def search(query,*,approved=None,halt_check=None,transport=None,clock=None):
    def require_consent():
        decision=decide_canada_read(approved=approved,halted=halt_check() if callable(halt_check) else None)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require_consent()
    if type(query) is not CanadaQuery:
        raise ValueError("validated CanadaBuys query required")
    keyword=query.validated()
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    now=clock()
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware clock required")
    now=now.astimezone(timezone.utc)
    request=_request if transport is None else transport
    try:
        status,raw,last_modified=request()
    except Exception:
        raise SearchError("CANADA_TRANSPORT_FAILURE") from None
    require_consent()
    if status==429:
        raise SearchError("CANADA_RATE_LIMIT_STOP")
    if status==403:
        raise SearchError("CANADA_ACCESS_DENIED_STOP")
    if status!=200:
        raise SearchError("CANADA_HTTP_FAILURE")
    if type(raw) is not bytes or len(raw)>MAX_BYTES:
        raise SearchError("CANADA_RESPONSE_TOO_LARGE_OR_INVALID")
    observed=clock()
    if type(observed) is not datetime or observed.utcoffset() is None:
        raise ValueError("aware retrieval time required")
    observed=observed.astimezone(timezone.utc)
    if observed<now:
        raise SearchError("CANADA_CLOCK_MOVED_BACKWARD")
    stamp,freshness=_dataset_time(last_modified,observed)
    seen=set()
    leads=[]
    count=0
    try:
        text=raw.decode("utf-8-sig")
        # CSV's limit is process-wide. Serialize the temporary override and restore it.
        with CSV_LOCK:
            previous=csv.field_size_limit(MAX_FIELD)
            try:
                reader=csv.reader(io.StringIO(text,newline=""),strict=True)
                header=next(reader)
                if not 1<=len(header)<=128 or len(set(header))!=len(header) or not REQUIRED<=set(header):
                    raise ValueError("unexpected CSV schema")
                fields=[field for field in STATUS_FIELDS if field in header]
                if len(fields)!=1:
                    raise ValueError("missing or ambiguous status column")
                for values in reader:
                    count+=1
                    if count>MAX_ROWS or len(values)!=len(header):
                        raise ValueError("row cap or malformed row")
                    if count%100==0:
                        require_consent()
                    row=dict(zip(header,values))
                    reference=row[REFERENCE]
                    notice_url(reference)
                    identity=reference.casefold()
                    if identity in seen:
                        raise ValueError("duplicate notice reference")
                    seen.add(identity)
                    if keyword in (row[TITLE]+" "+row.get(FRENCH_TITLE,"")).casefold():
                        leads.append(_lead(row,fields[0],observed,freshness))
            finally:
                csv.field_size_limit(previous)
    except (csv.Error,ValueError,TypeError,KeyError,UnicodeError,OverflowError,StopIteration):
        raise SearchError("CANADA_CSV_INVALID_OR_SCHEMA_CHANGED") from None
    require_consent()
    leads.sort(key=lambda row:(not row["research_candidate"],
        row["earliest_deadline_date"] or "9999",row["notice_id"]))
    matches=len(leads)
    return dict(format=FORMAT,scope="Public daily snapshot research; no execution eligibility",
        source="CanadaBuys",source_file=DATA_URL,
        attribution="Contains information licensed under the Open Government Licence – Canada.",
        query={"title_keyword":keyword},requests=1,reported_total=matches,returned=min(matches,MAX_RESULTS),
        source_row_count=count,truncated=matches>MAX_RESULTS,
        source_last_modified=stamp.isoformat() if stamp else None,
        dataset_freshness=freshness or "WITHIN_48_HOUR_HTTP_METADATA_WINDOW",
        page_sha256=[hashlib.sha256(raw).hexdigest()],leads=leads[:MAX_RESULTS])
