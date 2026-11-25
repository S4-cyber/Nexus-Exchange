"""Deterministic offline screening; never grants commercial authority."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from .scout import Opportunity

@dataclass(frozen=True, slots=True)
class Screening:
    eligible_for_review: bool
    reasons: tuple[str, ...]

def screen(opportunity, *, now, max_age=timedelta(hours=24)):
    if type(opportunity) is not Opportunity:
        raise ValueError("normalized opportunity required")
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware evaluation time required")
    if type(max_age) is not timedelta or max_age <= timedelta(0):
        raise ValueError("positive freshness window required")
    now = now.astimezone(timezone.utc)
    reasons = []
    if opportunity.retrieved_at > now:
        reasons.append("FUTURE_OBSERVATION")
    elif now - opportunity.retrieved_at > max_age:
        reasons.append("STALE_OBSERVATION")
    if opportunity.deadline is None:
        reasons.append("MISSING_DEADLINE")
    elif opportunity.deadline <= now:
        reasons.append("DEADLINE_PASSED")
    if opportunity.amount is None or opportunity.currency is None:
        reasons.append("MISSING_VALUE")
    elif not opportunity.amount.is_finite() or opportunity.amount <= 0:
        reasons.append("INVALID_VALUE")
    return Screening(not reasons, tuple(reasons))
