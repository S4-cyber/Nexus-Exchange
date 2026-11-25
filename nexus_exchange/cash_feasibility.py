"""Lead-bound, explicitly hypothetical USD cash and delivery model.

No extraction of contract values, authorization, source validation or actual income.
All modeled costs are reserved before payment, even if delivery fails.
"""
import hashlib
import json
from decimal import Context, Decimal, localcontext
import re
from .checklist_store import context_for
from .governor import Action, decide
from .owner_profile import normalize_profile, profile_revision

COSTS=("platform_fees","software","materials","subcontracting","taxes","deposits","other")
FIELDS={"currency","compensation","probability_delivery_bps","probability_payment_given_delivery_bps",
    "delivery_days","payment_days_after_delivery","labor_hours","costs"}

def _money(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?",value):
        raise ValueError("bounded USD amount or unknown required")
    return Decimal(value)

def _bounded(value,maximum):
    if value is None:
        return None
    if type(value) is not int or not 0<=value<=maximum:
        raise ValueError("bounded nonnegative integer or unknown required")
    return value

def assess(*,lead,profile,scenario,halted=None):
    decision=decide(Action.SIMULATE,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    context=context_for(lead)
    profile=normalize_profile(profile)
    if context["profile_revision"]!=profile_revision(profile):
        raise ValueError("scenario requires matching owner profile revision")
    if type(scenario) is not dict or set(scenario)!=FIELDS or scenario["currency"]!="USD":
        raise ValueError("complete USD scenario required")
    costs=scenario["costs"]
    if type(costs) is not dict or set(costs)!=set(COSTS):
        raise ValueError("all cost categories required; use null for unknown")
    costs={k:_money(costs[k]) for k in COSTS}
    fee=_money(scenario["compensation"])
    delivery=_bounded(scenario["probability_delivery_bps"],10000)
    payment=_bounded(scenario["probability_payment_given_delivery_bps"],10000)
    days=_bounded(scenario["delivery_days"],3650)
    paydays=_bounded(scenario["payment_days_after_delivery"],3650)
    hours=_bounded(scenario["labor_hours"],87600)
    reasons=["ASSUMPTIONS_NOT_INDEPENDENTLY_VERIFIED"]
    reasons.extend("COST_UNKNOWN:"+k for k,v in costs.items() if v is None)
    for key,value in (("COMPENSATION",fee),("DELIVERY_PROBABILITY",delivery),
            ("PAYMENT_PROBABILITY",payment),("DELIVERY_DAYS",days),("PAYMENT_DAYS",paydays),("LABOR_HOURS",hours)):
        if value is None:
            reasons.append(key+"_UNKNOWN")
    with localcontext(Context(prec=60)):
        exposure=None if None in costs.values() else sum(costs.values(),Decimal(0))
        expected=None if None in (fee,delivery,payment,exposure) else (
            fee*Decimal(delivery)*Decimal(payment)/Decimal(100000000)-exposure)
        budget_fit=None if exposure is None else exposure<=Decimal(profile["budget"])
        # Compare integer hour-days to avoid rounding and ambient decimal context.
        hours_fit=None if None in (hours,days) else hours*7<=profile["hours_per_week"]*days
        if budget_fit is False:
            reasons.append("MODELED_EXPOSURE_EXCEEDS_BUDGET")
        if hours_fit is False:
            reasons.append("MODELED_HOURS_EXCEED_DECLARED_AVAILABILITY")
        if expected is not None and expected<=0:
            reasons.append("MODELED_NONPOSITIVE_NET")
        normalized=dict(scenario,compensation=None if fee is None else format(fee,".2f"),
            costs={k:None if v is None else format(v,".2f") for k,v in costs.items()})
    if context["source"]=="usaspending":
        reasons.append("CONTRACTOR_INTELLIGENCE_NOT_SOLICITATION")
    if not lead.get("research_candidate_at_collection"):
        reasons.append("NOT_RESEARCH_CANDIDATE_AT_COLLECTION")
    if lead.get("blockers"):
        reasons.append("SOURCE_BLOCKERS_REQUIRE_REVIEW")
    payload=json.dumps(dict(context=context,scenario=normalized),sort_keys=True,separators=(",",":"),ensure_ascii=True)
    return dict(context=context,scenario_sha256=hashlib.sha256(payload.encode("ascii")).hexdigest(),
        modeled_cash_exposure=exposure,modeled_expected_net=expected,modeled_budget_fit=budget_fit,
        modeled_hours_fit=hours_fit,modeled_days_to_payment=None if None in (days,paydays) else days+paydays,
        reasons=tuple(reasons),independently_verified=False,genesis_verified=False,
        execution_eligible=False,external_authority=False)
