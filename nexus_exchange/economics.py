"""Offline, assumption-driven intermediary economics. No commitment authority."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Context, Decimal, localcontext
import re
from .atlas import Candidate, qualify_suppliers
from .governor import Action, decide
from .scout import _text

_FIELDS = {"currency","fee_if_collected","upfront_cost","completion_cost",
           "probability_completion","probability_collection_given_completion",
           "exposure_limit","assumptions"}

@dataclass(frozen=True, slots=True)
class DealAssessment:
    candidate: Candidate
    currency: str
    fee_if_collected: Decimal
    upfront_cost: Decimal
    completion_cost: Decimal
    probability_completion: Decimal
    probability_collection_given_completion: Decimal
    exposure_limit: Decimal
    assumptions: str
    expected_fee: Decimal
    expected_cost: Decimal
    expected_net: Decimal
    net_if_paid: Decimal
    maximum_modeled_loss: Decimal
    eligible_for_review: bool
    reasons: tuple[str,...]
    external_authority: bool = False

def _money(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,4})?",value):
        raise ValueError("bounded nonnegative decimal money required")
    return Decimal(value)

def _probability(value):
    if type(value) is not str or not re.fullmatch(r"[01](?:\.[0-9]{1,6})?",value):
        raise ValueError("bounded probability text required")
    result = Decimal(value)
    if not Decimal(0) <= result <= Decimal(1):
        raise ValueError("probability outside unit interval")
    return result

def assess_deal(opportunity,buyer,supplier,*,classifications,region,terms,now,
                halted=None,max_age=timedelta(hours=24)):
    """Estimate one fee-only scenario, using explicit assumptions, never tender value as revenue.

    Upfront costs apply in every modeled outcome; completion costs apply when
    completed, even if collection fails. Excludes unmodeled liabilities.
    """
    decision = decide(Action.SIMULATE,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    candidate = qualify_suppliers(opportunity,buyer,[supplier],classifications=classifications,
        region=region,now=now,halted=halted,max_age=max_age)[0]
    if type(terms) is not dict or set(terms) != _FIELDS:
        raise ValueError("complete economics assumptions required")
    currency = terms["currency"]
    if type(currency) is not str or not re.fullmatch("[A-Z]{3}",currency) or currency != opportunity.currency:
        raise ValueError("scenario currency must match opportunity")
    fee, upfront, completion, limit = (_money(terms[key]) for key in
        ("fee_if_collected","upfront_cost","completion_cost","exposure_limit"))
    p_complete = _probability(terms["probability_completion"])
    p_collect = _probability(terms["probability_collection_given_completion"])
    assumptions = _text(terms["assumptions"],1024)
    with localcontext(Context(prec=60)):
        expected_fee = fee * p_complete * p_collect
        expected_cost = upfront + completion * p_complete
        expected_net = expected_fee - expected_cost
        net_if_paid = fee - upfront - completion
        maximum_modeled_loss = upfront + completion
    reasons = list(candidate.reasons)
    if expected_net <= 0:
        reasons.append("NONPOSITIVE_EXPECTED_NET")
    if maximum_modeled_loss > limit:
        reasons.append("EXPOSURE_LIMIT_EXCEEDED")
    return DealAssessment(candidate,currency,fee,upfront,completion,p_complete,p_collect,
        limit,assumptions,expected_fee,expected_cost,expected_net,net_if_paid,maximum_modeled_loss,
        not reasons,tuple(reasons))
