"""Bounded deterministic ordering of historical Scout opportunities for review.

This is not evidence verification, an income predictor, or transaction authority.
One archive read snapshot is used; the newest exact-context plan is selected
without optimizing over alternative owner-declared assumptions.
"""
from decimal import Decimal
from .cash_feasibility import assess
from .checklist_store import context_for
from .lead_store import _now, _permit
from .owner_profile import normalize_profile, BLOCKED_REASONS
from .scenario_store import ScenarioStore
from .schedule_feasibility import assess_schedule, _iso
from .scout import _timestamp

MAX_SCAN=100
TIERS=(
    "MODEL_FITS_UNVERIFIED","MODEL_UNRESOLVED","MODEL_DOES_NOT_FIT",
    "SOURCE_REVIEW_REQUIRED","CONTRACTOR_INTELLIGENCE_ONLY","SOURCE_NOT_SELECTED",
)
DAY_US=86400*1000000


def _collection_wait(now, schedule, saved):
    finish=schedule["modeled_delivery_finish"]
    delay=saved["scenario"]["payment_days_after_delivery"]
    if finish is None or delay is None:
        return None
    elapsed=_timestamp(finish)-now
    # Exact elapsed time, including the modeled wait until contract start.
    return elapsed.days*DAY_US+elapsed.seconds*1000000+elapsed.microseconds+delay*DAY_US


def _source_tier(lead):
    fit=lead["profile_fit"]
    if fit["reason"]=="SOURCE_NOT_SELECTED":
        return "SOURCE_NOT_SELECTED"
    if lead["source"]=="usaspending":
        return "CONTRACTOR_INTELLIGENCE_ONLY"
    if (fit["priority"]>=3 or not lead["research_candidate_at_collection"]
            or lead["collection_truncated"] or BLOCKED_REASONS.intersection(lead["blockers"])):
        return "SOURCE_REVIEW_REQUIRED"
    return None


def _sort_key(row):
    tier=TIERS.index(row["review_tier"])
    # Compare hypothetical economics only for complete, positive, source-fit
    # models. Missing/negative values do not accidentally sort as zero.
    if tier==0:
        return (tier,row["profile_priority"],row["modeled_cash_exposure"],
                row["modeled_collection_wait_us"],row["modeled_expected_net"].copy_negate())
    return (tier,row["profile_priority"])


class RankingStore(ScenarioStore):
    def rank_review(self,*,profile,now,source=None,query="",limit=25,scan_limit=100,halted=None):
        """Rank a bounded window selected by existing profile/history ordering.

        All returned rows are for research only. A truncated scan never claims
        a global rank. Neither arbitrary score weights nor evidence assertions
        can override a source hold. The trusted caller supplies the profile,
        clock and halt state; no profile authentication is implied.
        """
        _permit(halted)
        now=_now(now)
        profile=normalize_profile(profile)
        if (type(scan_limit) is not int or not 1<=scan_limit<=MAX_SCAN
                or type(limit) is not int or not 1<=limit<=scan_limit):
            raise ValueError("invalid ranking bounds")
        self.db.execute("BEGIN")
        try:
            history=self.browse(now=now,profile=profile,source=source,query=query,
                                limit=scan_limit,halted=halted)
            rows=[]
            for lead in history["leads"]:
                rows.append(self._rank_row(lead,profile,now,halted))
            rows.sort(key=_sort_key)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return dict(format="nexus-scout-review-ranking-v1",evaluated_at=_iso(now),
            profile_revision=history["profile_revision"],pathway=profile["mode"],
            matched=history["matched"],evaluated=len(rows),returned=min(len(rows),limit),
            scan_truncated=history["truncated"],output_truncated=len(rows)>limit,
            global_ranking=False,rows=rows[:limit],independently_verified=False,
            execution_eligible=False,external_authority=False)

    def _rank_row(self,lead,profile,now,halted):
        context=context_for(lead)
        source_tier=_source_tier(lead)
        reasons=list(lead["blockers"])+[lead["profile_fit"]["reason"],
                                       "REVIEW_ORDER_ONLY_NOT_VERIFIED"]
        if lead["collection_truncated"]:
            reasons.append("COLLECTION_TRUNCATED")
        plans=self.list(context,limit=2,halted=halted)
        chosen=None
        exposure=expected=wait=None
        budget_fit=schedule_fit=None
        scenario_hash=schedule_hash=None
        model_tier="MODEL_UNRESOLVED"
        if not plans:
            reasons.append("NO_CURRENT_SCENARIO")
        elif _timestamp(plans[0]["created_at"])>now:
            reasons.append("SCENARIO_IN_FUTURE")
        elif len(plans)>1 and plans[0]["created_at"]==plans[1]["created_at"]:
            reasons.append("LATEST_SCENARIO_AMBIGUOUS")
        elif _timestamp(context["retrieved_at"])>now:
            reasons.append("OBSERVATION_IN_FUTURE")
        else:
            saved=plans[0]
            chosen=saved["plan_id"]
            cash=assess(lead=lead,profile=profile,scenario=saved["scenario"],halted=halted)
            schedule=assess_schedule(lead=lead,profile=profile,scenario=saved["scenario"],
                                     plan=saved["plan"],now=now,halted=halted)
            exposure=cash["modeled_cash_exposure"]
            expected=cash["modeled_expected_net"]
            budget_fit=cash["modeled_budget_fit"]
            schedule_fit=schedule["modeled_schedule_fit"]
            wait=_collection_wait(now,schedule,saved)
            scenario_hash=cash["scenario_sha256"]
            schedule_hash=schedule["schedule_sha256"]
            reasons.extend(cash["reasons"])
            reasons.extend(schedule["reasons"])
            if budget_fit is False or schedule_fit is False or (expected is not None and expected<=0):
                model_tier="MODEL_DOES_NOT_FIT"
            elif (budget_fit is True and schedule_fit is True and exposure is not None
                    and expected is not None and expected>0 and wait is not None and wait>=0):
                model_tier="MODEL_FITS_UNVERIFIED"
            else:
                reasons.append("MODELED_INPUTS_UNRESOLVED")
        return dict(source=lead["source"],title=lead["title"],source_url=lead["source_url"],
            notice_id=lead["notice_id"],context=context,profile_priority=lead["profile_fit"]["priority"],
            review_tier=source_tier or model_tier,model_tier=model_tier,plan_id=chosen,
            scenario_sha256=scenario_hash,schedule_sha256=schedule_hash,
            modeled_cash_exposure=exposure,modeled_expected_net=expected,
            modeled_collection_wait_us=wait,modeled_budget_fit=budget_fit,modeled_schedule_fit=schedule_fit,
            reasons=tuple(dict.fromkeys(reasons)),independently_verified=False,
            genesis_verified=False,execution_eligible=False,external_authority=False)
