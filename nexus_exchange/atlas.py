"""Review-only matching using declared organization, capacity and classification evidence.

OCDS-inspired scheme-scoped identifiers and classifications. Source assertions
are not verified identity, credit, licensing, consent or authority to contact.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import re
from .governor import Action, decide
from .scout import _text, _timestamp, _url, Opportunity, normalize
from .council_screen import screen

MAX_SUPPLIERS = 100
MAX_CODES = 32
FIELDS = {"scheme","identifier","name","roles","classifications","regions",
          "currency","capacity","source_url","observed_at"}

def _canonical(value, limit):
    value_checked = _text(value,limit)
    if value != value_checked:
        raise ValueError("noncanonical text")
    return value_checked

def _scheme(value):
    value = _canonical(value,64)
    if not re.fullmatch("[A-Z0-9][A-Z0-9_-]{0,63}",value):
        raise ValueError("invalid scheme")
    return value

def _list(values, limit):
    if type(values) is not list or not 1 <= len(values) <= limit:
        raise ValueError("bounded nonempty list required")
    return values

def _unique(values):
    if len(set(values)) != len(values):
        raise ValueError("duplicate value")
    return tuple(sorted(values))

def _classifications(values):
    codes = []
    for item in _list(values, MAX_CODES):
        if type(item) is not dict or set(item) != {"scheme","code"}:
            raise ValueError("classification scheme and code required")
        codes.append((_scheme(item["scheme"]),_canonical(item["code"],128)))
    return _unique(codes)

def _region(value):
    value = _canonical(value,32)
    if not re.fullmatch("[A-Z]{2}(?:-[A-Z0-9]{1,12})?",value):
        raise ValueError("invalid region format")
    return value

@dataclass(frozen=True,slots=True)
class Counterparty:
    key: str
    scheme: str
    identifier: str
    name: str
    roles: tuple[str,...]
    classifications: tuple[tuple[str,str],...]
    regions: tuple[str,...]
    currency: str
    capacity: Decimal
    source_url: str
    observed_at: datetime

@dataclass(frozen=True,slots=True)
class Candidate:
    opportunity_key: str
    buyer: Counterparty
    supplier: Counterparty
    eligible_for_review: bool
    reasons: tuple[str,...]

def normalize_party(raw):
    if type(raw) is not dict or set(raw) != FIELDS:
        raise ValueError("invalid counterparty schema")
    scheme = _scheme(raw["scheme"])
    identifier = _canonical(raw["identifier"],128)
    name = _canonical(raw["name"],256)
    roles = _unique([_canonical(x,16) for x in _list(raw["roles"],2)])
    if not set(roles) <= {"buyer","supplier"}:
        raise ValueError("unsupported role")
    currency = _canonical(raw["currency"],3)
    if not re.fullmatch("[A-Z]{3}",currency):
        raise ValueError("invalid currency")
    capacity = raw["capacity"]
    if type(capacity) is not str or not re.fullmatch(r"\d{1,12}(?:\.\d{1,4})?",capacity):
        raise ValueError("invalid capacity")
    capacity = Decimal(capacity)
    if capacity <= 0:
        raise ValueError("positive capacity required")
    key = hashlib.sha256(json.dumps([scheme,identifier],ensure_ascii=True,separators=(",",":")).encode()).hexdigest()
    return Counterparty(key,scheme,identifier,name,roles,_classifications(raw["classifications"]),
        _unique([_region(x) for x in _list(raw["regions"],32)]),currency,capacity,
        _url(raw["source_url"]),_timestamp(raw["observed_at"]))

def _party_reasons(party, role, opportunity, codes, region, now, max_age):
    prefix = role.upper() + "_"
    reasons = []
    if role not in party.roles:
        reasons.append(prefix+"ROLE_MISSING")
    if not set(codes) <= set(party.classifications):
        reasons.append(prefix+"CLASSIFICATION_MISSING")
    if region not in party.regions:
        reasons.append(prefix+"REGION_MISMATCH")
    if party.currency != opportunity.currency:
        reasons.append(prefix+"CURRENCY_MISMATCH")
    elif opportunity.amount is not None and party.capacity < opportunity.amount:
        reasons.append(prefix+"CAPACITY_INSUFFICIENT")
    if party.observed_at > now:
        reasons.append(prefix+"FUTURE_OBSERVATION")
    elif now-party.observed_at > max_age:
        reasons.append(prefix+"STALE_OBSERVATION")
    return reasons

def qualify_suppliers(opportunity,buyer_raw,supplier_raws,*,classifications,region,now,
                      halted=None,max_age=timedelta(hours=24)):
    """Evaluate at most 100 candidates, exact matching only, no dispatch authority."""
    decision = decide(Action.EVALUATE,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    if type(opportunity) is not Opportunity:
        raise ValueError("normalized opportunity required")
    canonical = normalize(dict(source=opportunity.source,external_id=opportunity.external_id,
        title=opportunity.title,source_url=opportunity.source_url,
        retrieved_at=opportunity.retrieved_at.isoformat(),
        deadline=opportunity.deadline.isoformat() if opportunity.deadline else None,
        currency=opportunity.currency,amount=format(opportunity.amount,"f") if opportunity.amount is not None else None))
    if canonical != opportunity:
        raise ValueError("noncanonical opportunity")
    result = screen(opportunity,now=now,max_age=max_age)
    codes, region = _classifications(classifications), _region(region)
    buyer = normalize_party(buyer_raw)
    if type(supplier_raws) is not list or len(supplier_raws)>MAX_SUPPLIERS:
        raise ValueError("bounded supplier list required")
    suppliers = [normalize_party(raw) for raw in supplier_raws]
    if len({p.key for p in suppliers}) != len(suppliers):
        raise ValueError("duplicate supplier identity")
    common = ["OPPORTUNITY_"+reason for reason in result.reasons]
    common += _party_reasons(buyer,"buyer",opportunity,codes,region,now,max_age)
    rows = []
    for supplier in sorted(suppliers,key=lambda p:p.key):
        reasons = list(common)
        if supplier.key == buyer.key:
            reasons.append("SAME_ORGANIZATION")
        reasons += _party_reasons(supplier,"supplier",opportunity,codes,region,now,max_age)
        rows.append(Candidate(opportunity.key,buyer,supplier,not reasons,tuple(reasons)))
    return tuple(rows)
