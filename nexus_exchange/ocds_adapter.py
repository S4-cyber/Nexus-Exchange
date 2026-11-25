"""Offline mapping of complete active tender snapshots; not an OCDS compiler."""
from dataclasses import dataclass
from decimal import Decimal
from .scout import Opportunity, normalize, _timestamp
from .ocds_identity import release_identity

@dataclass(frozen=True, slots=True)
class TenderObservation:
    opportunity: Opportunity
    release_key: str
    published_at: object

def map_active_tender(publisher, release, source_url, retrieved_at):
    key = release_identity(publisher, release)
    if publisher != publisher.strip():
        raise ValueError("noncanonical publisher")
    published = _timestamp(release.get("date"))
    retrieved = _timestamp(retrieved_at)
    if published > retrieved:
        raise ValueError("future publication")
    tender = release.get("tender")
    if type(tender) is not dict or tender.get("status") != "active":
        raise ValueError("active tender snapshot required")
    period = tender.get("tenderPeriod")
    if type(period) is not dict:
        raise ValueError("deadline required")
    deadline = _timestamp(period.get("endDate"))
    if deadline <= retrieved:
        raise ValueError("expired tender")
    value = tender.get("value")
    if type(value) is not dict:
        raise ValueError("value required")
    amount = value.get("amount")
    if type(amount) not in (int, Decimal):
        raise ValueError("parse JSON decimals losslessly")
    if not Decimal(amount).is_finite():
        raise ValueError("nonfinite amount")
    opportunity = normalize(dict(source=publisher, external_id=key,
        title=tender.get("title"), source_url=source_url,
        retrieved_at=retrieved_at, deadline=period["endDate"],
        currency=value.get("currency"), amount=format(Decimal(amount),"f")))
    return TenderObservation(opportunity, key, published)
