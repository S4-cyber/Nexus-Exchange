"""Atlas read-only SEC filer metadata; no legal, credit or identity clearance."""
from datetime import date, datetime, timezone
from hashlib import sha256
import http.client
import json
import re
from threading import Lock
from time import monotonic_ns
import unicodedata

from .governor import Action, decide, decide_sec_read
from .local_import import _pairs, _integer, _decimal, _constant

HOST="data.sec.gov"
FORMAT="nexus-atlas-sec-company-v1"
MAX_BYTES=8*1024*1024
MAX_RECENT_ROWS=10000
MAX_DISPLAY=12
FORMS=frozenset(("10-K","10-K/A","10-Q","10-Q/A","8-K","8-K/A",
                 "20-F","20-F/A","40-F","40-F/A","6-K","6-K/A"))
_GATE=Lock()
_LAST_REQUEST_NS=None
_INTERVAL_NS=1_000_000_000


class SecError(ValueError):
    """Stable reason codes; no provider body or declared contact in errors."""


def normalize_cik(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,10}",value):
        raise ValueError("CIK must be 1–10 ASCII digits")
    if int(value)==0:
        raise ValueError("positive CIK required")
    return value.zfill(10)


def _declared_agent(organization,email):
    if (type(organization) is not str or not 1<=len(organization)<=80
            or organization!=organization.strip()
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,&'()_-]*",organization)):
        raise ValueError("valid declared organization required")
    if (type(email) is not str or len(email)>160
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+%-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",email)):
        raise ValueError("valid declared business contact required")
    return "NexusExchange-Preview/1 "+organization+" "+email


def source_url(cik):
    return "https://"+HOST+"/submissions/CIK"+normalize_cik(cik)+".json"


def _stamp(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware evaluation clock required")
    return now.astimezone(timezone.utc)


def _text(value,limit):
    if (type(value) is not str or not 1<=len(value)<=limit or not value.strip()
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise ValueError("invalid metadata text")
    return value.strip()


def _optional_text(value,limit):
    if value is None or value=="":
        return None
    return _text(value,limit)


def _reported_cik(value):
    if type(value) is int:
        value=str(value)
    return normalize_cik(value)


def _filing_date(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValueError("invalid filing date")
    return date.fromisoformat(value)


def _filings(data,cik,now):
    section=data.get("filings")
    if type(section) is not dict or type(section.get("recent")) is not dict:
        raise ValueError("invalid recent filing metadata")
    recent=section["recent"]
    cols=[recent.get(key) for key in ("accessionNumber","filingDate","form")]
    if any(type(col) is not list for col in cols):
        raise ValueError("invalid filing columns")
    size=len(cols[0])
    if size>MAX_RECENT_ROWS or any(len(col)!=size for col in cols):
        raise ValueError("unbounded or misaligned filing columns")
    seen=set()
    rows=[]
    for accession,stamp,form in zip(*cols):
        if type(accession) is not str or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",accession):
            raise ValueError("invalid accession number")
        if accession in seen:
            raise ValueError("duplicate accession number")
        seen.add(accession)
        filed=_filing_date(stamp)
        if filed>now.date():
            raise ValueError("future filing date")
        form=_text(form,32)
        if form in FORMS:
            # Do not trust a returned primaryDocument, filename or URL.
            url=("https://www.sec.gov/Archives/edgar/data/"+str(int(cik))+"/"
                 +accession.replace("-","")+"/"+accession+"-index.html")
            rows.append(dict(accession_number=accession,filing_date=stamp,form=form,source_url=url))
    rows.sort(key=lambda row:(row["filing_date"],row["accession_number"]),reverse=True)
    return size,len(rows),rows[:MAX_DISPLAY]


def parse_company(raw,cik,*,expected_name=None,now,halted=None):
    """Project only operating-company metadata from bounded raw source bytes."""
    if not decide(Action.RESEARCH_LOCAL,halted=halted).allowed:
        raise PermissionError("HALTED_OR_UNKNOWN")
    cik=normalize_cik(cik)
    now=_stamp(now)
    if expected_name is not None:
        expected_name=_text(expected_name,256)
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BYTES:
        raise SecError("SEC_RESPONSE_SIZE")
    try:
        data=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
                        parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
        if type(data) is not dict or _reported_cik(data.get("cik"))!=cik:
            raise SecError("SEC_CIK_MISMATCH")
        if data.get("entityType")!="operating":
            raise SecError("SEC_UNSUPPORTED_ENTITY_TYPE")
        name=_text(data.get("name"),256)
        sic=data.get("sic")
        if sic in ("",None):
            sic=None
        elif type(sic) is not str or not re.fullmatch(r"[0-9]{4}",sic):
            raise ValueError("invalid SIC")
        description=_optional_text(data.get("sicDescription"),256)
        tickers=data.get("tickers",[])
        if type(tickers) is not list or len(tickers)>64:
            raise ValueError("invalid tickers")
        tickers=[_text(ticker,24) for ticker in tickers]
        if len(set(tickers))!=len(tickers):
            raise ValueError("duplicate ticker")
        count,matched,filings=_filings(data,cik,now)
        comparison=("NOT_SUPPLIED" if expected_name is None else
                    "EXACT_CASEFOLD_MATCH" if name.casefold()==expected_name.casefold() else "MISMATCH")
        reasons=["SOURCE_ASSERTIONS_ONLY","INDEPENDENT_IDENTITY_REVIEW_REQUIRED",
                 "AUTHORITY_AND_CAPACITY_UNVERIFIED","NO_CURRENT_BUYER_DEMAND_EVIDENCE"]
        if comparison=="MISMATCH":
            reasons.append("DECLARED_NAME_MISMATCH")
        if not filings:
            reasons.append("NO_SELECTED_RECENT_FORMS")
        return dict(format=FORMAT,source="SEC EDGAR",source_url=source_url(cik),
            classification="PUBLIC_FILER_METADATA_ONLY",cik=cik,reported_name=name,
            declared_name=expected_name,name_comparison=comparison,entity_type="operating",
            sic=sic,sic_description=description,tickers=tickers,evaluated_at=now.isoformat(),
            recent_rows_observed=count,selected_forms_observed=matched,filings=filings,
            display_truncated=matched>MAX_DISPLAY,filing_history_complete=False,
            raw_sha256=sha256(raw).hexdigest(),reasons=reasons,
            independently_verified=False,identity_verified=False,solvency_verified=False,
            capacity_verified=False,contact_permission=False,commercial_facts_verified=False,
            research_only=True,execution_eligible=False,external_authority=False,
            zero_capital_verified=False)
    except SecError:
        raise
    except (ValueError,TypeError,KeyError,ArithmeticError,UnicodeError,RecursionError):
        raise SecError("SEC_RESPONSE_INVALID") from None


def _request(cik,user_agent):
    """Fixed GET; one in flight and at least one second between starts per process."""
    global _LAST_REQUEST_NS
    if not _GATE.acquire(blocking=False):
        raise SecError("SEC_LOCAL_REQUEST_BUSY")
    connection=None
    try:
        now=monotonic_ns()
        if _LAST_REQUEST_NS is not None and now-_LAST_REQUEST_NS<_INTERVAL_NS:
            raise SecError("SEC_LOCAL_RATE_LIMIT")
        _LAST_REQUEST_NS=now
        path="/submissions/CIK"+normalize_cik(cik)+".json"
        connection=http.client.HTTPSConnection(HOST,443,timeout=10)
        connection.request("GET",path,headers={"Accept":"application/json",
            "Accept-Encoding":"identity","User-Agent":user_agent})
        response=connection.getresponse()
        if response.status!=200:
            return response.status,b""
        media=response.getheader("Content-Type","").split(";",1)[0].strip().lower()
        if media!="application/json" or response.getheader("Content-Encoding","identity").lower()!="identity":
            raise SecError("SEC_RESPONSE_MEDIA")
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise SecError("SEC_RESPONSE_SIZE")
        return response.status,raw
    except SecError:
        raise
    except Exception:
        raise SecError("SEC_TRANSPORT_FAILURE") from None
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            _GATE.release()


def fetch_company(cik,organization,email,*,expected_name=None,approved=None,
                  halt_check=None,transport=None,clock=None):
    """One owner-consented request; contact appears only in SEC's required header."""
    def require():
        state=halt_check() if callable(halt_check) else None
        decision=decide_sec_read(approved=approved,halted=state)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require()
    cik=normalize_cik(cik)
    agent=_declared_agent(organization,email)
    if expected_name is not None:
        expected_name=_text(expected_name,256)
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    start=_stamp(clock())
    require()
    request=_request if transport is None else transport
    try:
        status,raw=request(cik,agent)
    except SecError:
        raise
    except Exception:
        raise SecError("SEC_TRANSPORT_FAILURE") from None
    require()
    if type(status) is not int or status!=200:
        raise SecError("SEC_ACCESS_OR_RATE_LIMIT_STOP" if status in (403,429) else
                       "SEC_NOT_FOUND" if status==404 else "SEC_HTTP_FAILURE")
    now=_stamp(clock())
    if now<start:
        raise SecError("SEC_CLOCK_REGRESSION")
    result=parse_company(raw,cik,expected_name=expected_name,now=now,halted=False)
    require()
    return dict(result,requests=1,retrieved_at=now.isoformat(),
                transport="HTTPS_PUBLIC_METADATA_REQUEST",authenticated_origin=False)
