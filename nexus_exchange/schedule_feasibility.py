"""Hypothetical preparation and delivery timing, never a submission or contract grant."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

from .cash_feasibility import assess
from .owner_profile import normalize_profile
from .scout import _timestamp

PLAN_FIELDS=frozenset(("preparation_days","preparation_hours","delivery_start","delivery_deadline"))


def _quantity(value, maximum):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("bounded nonnegative schedule quantity or null required")
    return value


def _iso(value):
    return None if value is None else value.isoformat(timespec="microseconds")


def _optional_timestamp(value):
    return None if value is None else _timestamp(value)


def _finish(start, days):
    if start is None or days is None:
        return None
    try:
        return start + timedelta(days=days)
    except OverflowError as exc:
        raise ValueError("schedule exceeds timestamp range") from exc


def _combined(fits):
    if False in fits:
        return False
    if None in fits:
        return None
    return True


def assess_schedule(*, lead, profile, scenario, plan, now, halted=None):
    """Project elapsed UTC days and average weekly capacity, not a booked calendar.

    Historical source cutoff is only for preparation/submission. Contract
    start and delivery deadline are separate, explicitly hypothetical inputs.
    This is a local model; callers must obtain the lead from the trusted
    archive and independently revalidate all assumptions before relying on it.
    """
    model=assess(lead=lead,profile=profile,scenario=scenario,halted=halted)
    if type(plan) is not dict or set(plan)!=PLAN_FIELDS:
        raise ValueError("complete schedule plan required")
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware evaluation time required")
    try:
        now=now.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid evaluation time") from exc
    if now<_timestamp(model["context"]["retrieved_at"]):
        raise ValueError("schedule evaluation predates observation")
    profile=normalize_profile(profile)
    prep_days=_quantity(plan["preparation_days"],3650)
    prep_hours=_quantity(plan["preparation_hours"],87600)
    start=_optional_timestamp(plan["delivery_start"])
    due=_optional_timestamp(plan["delivery_deadline"])
    reported=_optional_timestamp(lead.get("deadline"))
    # Date-only hints are never upgraded into a precise instant.
    date_hint=lead.get("earliest_deadline_date")
    if date_hint is not None:
        from datetime import date
        if type(date_hint) is not str or len(date_hint)!=10:
            raise ValueError("invalid date-only deadline hint")
        if date.fromisoformat(date_hint).isoformat()!=date_hint:
            raise ValueError("noncanonical date-only deadline hint")
    blockers=lead.get("blockers")
    if type(blockers) is not list or len(blockers)>128 or any(
            type(x) is not str or not 0<len(x)<=256 or not x.isprintable() for x in blockers):
        raise ValueError("invalid historical blockers")
    prep_finish=_finish(now,prep_days)
    delivery_finish=_finish(start,scenario["delivery_days"])
    reasons=list(model["reasons"])+["SCHEDULE_ASSUMPTIONS_NOT_VERIFIED",
                                     "HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED"]+blockers
    if model["context"]["source"]=="usaspending":
        submission_fit=False
        reasons.append("HISTORICAL_AWARD_NOT_SUBMISSION_OPPORTUNITY")
    elif reported is None:
        submission_fit=None
        reasons.append("SUBMISSION_DEADLINE_UNRESOLVED")
    elif reported<=now:
        submission_fit=False
        reasons.append("REPORTED_SUBMISSION_DEADLINE_PASSED")
    elif prep_finish is None:
        submission_fit=None
    else:
        # Finishing at the cutoff does not leave time to submit.
        submission_fit=prep_finish<reported
        if not submission_fit:
            reasons.append("MODELED_SUBMISSION_MISSES_DEADLINE")
    if prep_days is None:
        reasons.append("PREPARATION_DAYS_UNKNOWN")
    if prep_hours is None:
        reasons.append("PREPARATION_HOURS_UNKNOWN")
    prep_fit=None if None in (prep_days,prep_hours) else prep_hours*7<=profile["hours_per_week"]*prep_days
    if prep_fit is False:
        reasons.append("MODELED_PREPARATION_HOURS_EXCEED_AVAILABILITY")
    if start is None:
        reasons.append("DELIVERY_START_UNKNOWN")
    if due is None:
        reasons.append("DELIVERY_DEADLINE_UNKNOWN")
    if start is not None and start<now:
        sequence_fit=False
    elif start is None or prep_finish is None:
        sequence_fit=None
    else:
        sequence_fit=prep_finish<=start
    if sequence_fit is False:
        reasons.append("MODELED_DELIVERY_START_BEFORE_PREPARATION_FINISH")
    if due is None:
        delivery_fit=None
    elif due<now or (start is not None and due<start):
        delivery_fit=False
    elif delivery_finish is None:
        delivery_fit=None
    else:
        delivery_fit=delivery_finish<=due
    if delivery_fit is False:
        reasons.append("MODELED_DELIVERY_MISSES_DEADLINE")
    payload=dict(version=1,scenario_sha256=model["scenario_sha256"],
                 evaluated_at=_iso(now),reported_submission_deadline=_iso(reported),
                 earliest_deadline_date=date_hint,source_blockers=blockers,
                 plan=dict(preparation_days=prep_days,preparation_hours=prep_hours,
                           delivery_start=_iso(start),delivery_deadline=_iso(due)))
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()
    return dict(context=model["context"],scenario_sha256=model["scenario_sha256"],
                schedule_sha256=digest,evaluated_at=_iso(now),
                reported_submission_deadline=_iso(reported),
                modeled_preparation_finish=_iso(prep_finish),
                modeled_delivery_finish=_iso(delivery_finish),
                modeled_submission_fit=submission_fit,modeled_preparation_hours_fit=prep_fit,
                modeled_sequence_fit=sequence_fit,modeled_delivery_deadline_fit=delivery_fit,
                modeled_delivery_hours_fit=model["modeled_hours_fit"],
                modeled_schedule_fit=_combined((submission_fit,prep_fit,sequence_fit,
                                                delivery_fit,model["modeled_hours_fit"])),
                reasons=tuple(dict.fromkeys(reasons)),independently_verified=False,
                genesis_verified=False,execution_eligible=False,external_authority=False)
