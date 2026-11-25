"""Bounded Frankfurter v2 reference-rate research, no trading or settlement."""
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
import http.client
import json
import re

from .governor import decide_fx_read, Action, decide
from .local_import import _pairs, _integer, _decimal, _constant

HOST = "api.frankfurter.dev"
FORMAT = "nexus-fx-reference-v1"
MAX_BYTES = 8192
MAX_AGE_DAYS = 7
CURRENCIES = ("AUD","CAD","CHF","EUR","GBP","JPY","NZD","USD")


class FxError(ValueError):
    """Stable reason codes; do not surface external error bodies."""


def _currency(base):
    if type(base) is not str or base not in CURRENCIES or base=="USD":
        raise ValueError("supported non-USD base currency required")
    return base


def _amount(amount):
    if type(amount) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,4})?",amount):
        raise ValueError("bounded nonnegative decimal amount required")
    return Decimal(amount)


def _stamp(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware UTC evaluation clock required")
    return now.astimezone(timezone.utc)


def source_url(base):
    return "https://"+HOST+"/v2/rate/"+_currency(base)+"/USD"


def _request(base):
    path="/v2/rate/"+_currency(base)+"/USD"
    connection=http.client.HTTPSConnection(HOST,443,timeout=8)
    try:
        connection.request("GET",path,headers={"Accept":"application/json",
            "Accept-Encoding":"identity","User-Agent":"NexusExchange-Preview/1"})
        response=connection.getresponse()
        if response.status!=200:
            return response.status,b""
        media=response.getheader("Content-Type","").split(";",1)[0].strip().lower()
        if media!="application/json" or response.getheader("Content-Encoding","identity").lower()!="identity":
            raise FxError("FX_RESPONSE_MEDIA")
        body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:
            raise FxError("FX_RESPONSE_SIZE")
        return response.status,body
    except FxError:
        raise
    except Exception:
        raise FxError("FX_TRANSPORT_FAILURE") from None
    finally:
        connection.close()


def parse_reference(raw,base,amount,*,now,halted=None):
    """Convert one amount against an exact bounded reference response.

    Raw bytes can be imported as a local fixture; their digest is not proof
    of origin. All figures remain indicative, never settlement or eligibility.
    """
    if not decide(Action.SIMULATE,halted=halted).allowed:
        raise PermissionError("HALTED_OR_UNKNOWN")
    base=_currency(base)
    amount_value=_amount(amount)
    now=_stamp(now)
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BYTES:
        raise FxError("FX_RESPONSE_SIZE")
    try:
        data=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
            parse_int=_integer,parse_float=_decimal,parse_constant=_constant)
        if type(data) is not dict or set(data)!={"date","base","quote","rate"}:
            raise ValueError("FX_RESPONSE_SCHEMA")
        if data["base"]!=base or data["quote"]!="USD":
            raise ValueError("FX_PAIR_MISMATCH")
        stamp=data["date"]
        if type(stamp) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",stamp):
            raise ValueError("FX_DATE_INVALID")
        observed=date.fromisoformat(stamp)
        age=(now.date()-observed).days
        if age<0 or age>MAX_AGE_DAYS:
            raise FxError("FX_RATE_STALE_OR_FUTURE")
        rate=data["rate"]
        if type(rate) not in (Decimal,int):
            raise ValueError("FX_RATE_INVALID")
        rate=Decimal(rate)
        if not Decimal("0.00000001")<=rate<=Decimal("1000000"):
            raise ValueError("FX_RATE_INVALID")
        with localcontext(Context(prec=60,rounding=ROUND_HALF_EVEN)):
            exact=amount_value*rate
            estimate=exact.quantize(Decimal("0.01"))
        return dict(format=FORMAT,source="Frankfurter",source_url=source_url(base),
            reference_kind="BLENDED_REFERENCE_ONLY",rate_date=observed.isoformat(),
            evaluated_at=now.isoformat(),age_days=age,base=base,quote="USD",
            input_amount=format(amount_value,"f"),usd_reference_rate=format(rate,"f"),
            indicative_usd_unrounded=format(exact,"f"),indicative_usd=format(estimate,"f"),
            raw_sha256=sha256(raw).hexdigest(),commercial_facts_verified=False,
            independently_verified=False,execution_eligible=False,external_authority=False,
            settlement_rate=False,fees_included=False,zero_capital_verified=False)
    except FxError:
        raise
    except (ValueError,TypeError,KeyError,ArithmeticError,UnicodeError,RecursionError):
        raise FxError("FX_RESPONSE_INVALID") from None


def fetch_reference(base,amount,*,approved=None,halt_check=None,transport=None,clock=None):
    """One fixed HTTPS GET, no redirect follow/retry, no amount or user data transmitted."""
    def require():
        state=halt_check() if callable(halt_check) else None
        decision=decide_fx_read(approved=approved,halted=state)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    require()
    _currency(base)
    _amount(amount)
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    start=_stamp(clock())
    require()
    request=_request if transport is None else transport
    try:
        status,raw=request(base)
    except FxError:
        raise
    except Exception:
        raise FxError("FX_TRANSPORT_FAILURE") from None
    require()
    if type(status) is not int or status!=200:
        raise FxError("FX_RATE_LIMIT_STOP" if status==429 else "FX_HTTP_FAILURE")
    now=_stamp(clock())
    if now<start:
        raise FxError("FX_CLOCK_REGRESSION")
    result=parse_reference(raw,base,amount,now=now,halted=False)
    require()
    return dict(result,requests=1,retrieved_at=now.isoformat(),
                transport="HTTPS_REFERENCE_REQUEST",authenticated_origin=False)
