"""Fixed local Council research policy for exact immutable Scout scenarios.

This adapter uses locally validated plan inputs as integrity pins. Neither the
pins, local modeled-fit predicates nor reference counts establish independent
commercial facts. No source documents are read; no external actions occur.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .cash_feasibility import assess
from .council_attempts import CouncilAttemptStore, _hash
from .council_audit import POLICY, POLICY_SHA256, scope_for, validate_snapshot
from .council_coordinator import CouncilCoordinator, build_task
from .council_criterion_review import CriterionSpec, _permit
from .lead_store import _digest, _json, _now
from .owner_profile import ProfileStore, profile_revision
from .review_ranking import _source_tier, _collection_wait
from .scenario_evidence import ScenarioEvidenceStore, ASSUMPTION_FIELDS, _value
from .schedule_feasibility import assess_schedule, _iso

def _financial(cash):
    budget=cash["modeled_budget_fit"]
    expected=cash["modeled_expected_net"]
    if budget is False or (expected is not None and expected<=0):
        return False
    if budget is True and expected is not None and expected>0:
        return True
    return None


def _state(value):
    return ("UNRESOLVED" if value is None else
            "LOCAL_CHECK_FITS" if value is True else "LOCAL_CHECK_FAILS")


def _predicate(expected,verdict):
    def check(raw):
        return raw==expected and verdict is True
    return check


def _task_and_material(saved,values):
    """Pin immutable local inputs, not changing model results or reference counts."""
    scope=scope_for(saved["plan_id"])
    specs=[]
    artifacts={}
    for name,_ in POLICY:
        raw=_json(dict(version=1,criterion=name,plan_id=saved["plan_id"],
            context=saved["context"],scenario=saved["scenario"],plan=saved["plan"])).encode("ascii")
        verdict=values[name]
        specs.append(CriterionSpec(name,_digest(raw.decode("ascii")),_predicate(raw,verdict)))
        # Unresolved local criterion material is deliberately absent from
        # this attempt. Pinning the plan does not supply missing evidence.
        if verdict is not None:
            artifacts[name]=raw
    return build_task(scope,POLICY_SHA256,tuple(specs)),artifacts


class ScenarioCouncil:
    """Synchronous local policy adapter; exact saved plan only, no auto-dispatch."""
    def __init__(self,directory,*,halt_check,clock=None):
        if not callable(halt_check) or (clock is not None and not callable(clock)):
            raise ValueError("trusted halt and clock callbacks required")
        self.directory=Path(directory)
        self.halt_check=halt_check
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _permit(self):
        _permit(False,self.halt_check)

    def _profile(self):
        self._permit()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            profile=store.load(halted=False)
        if profile is None:
            raise ValueError("current declared owner profile required")
        self._permit()
        return profile

    def _confirm(self,profile):
        self._permit()
        if profile_revision(self._profile())!=profile_revision(profile):
            raise ValueError("owner profile changed during review")
        self._permit()

    @contextmanager
    def _snapshot(self,plan_id):
        self._permit()
        _hash(plan_id)
        profile=self._profile()
        now=_now(self.clock())
        self._permit()
        # Read one coherent local archive snapshot. The separate ledger
        # contains only historical review metadata, never ongoing permission.
        with ScenarioEvidenceStore(self.directory/"scout-leads.sqlite3") as store:
            with store._transaction(halted=False,halt_check=self.halt_check):
                saved,lead=store._saved(plan_id,profile,now,False,self.halt_check)
                refs=store._references(saved,now)
                cash=assess(lead=lead,profile=profile,scenario=saved["scenario"],halted=False)
                timing=assess_schedule(lead=lead,profile=profile,scenario=saved["scenario"],
                    plan=saved["plan"],now=now,halted=False)
                wait=_collection_wait(now,timing,saved)
                source_hold=_source_tier(lead)
                unknown=[key for key in ASSUMPTION_FIELDS if _value(saved,key) is None]
                missing=[key for key in ASSUMPTION_FIELDS if not refs[key]]
                referenced=len(ASSUMPTION_FIELDS)-len(missing)
                values=dict(source_and_capability=source_hold is None,
                    financial_model=_financial(cash),
                    delivery_schedule=timing["modeled_schedule_fit"],
                    collection_timing=None if wait is None else wait>=0,
                    reference_coverage=True if not unknown and not missing else None)
                task,artifacts=_task_and_material(saved,values)
                reasons=list(lead["blockers"])+[lead["profile_fit"]["reason"]]
                if source_hold is not None:
                    reasons.append(source_hold)
                reasons.extend(cash["reasons"])
                reasons.extend(timing["reasons"])
                reasons.extend("REFERENCE_REQUIRED:"+key for key in missing)
                reasons.extend("ASSUMPTION_UNKNOWN:"+key for key in unknown)
                reasons.append("LOCAL_CHECKS_ONLY_NOT_INDEPENDENT_VERIFICATION")
                result=dict(format="nexus-scout-local-council-snapshot-v1",
                    plan_id=plan_id,context=saved["context"],evaluated_at=_iso(now),
                    task_id="COUNCIL."+task.scope_sha256,policy_sha256=POLICY_SHA256,
                    criteria=[dict(criterion=name,description=description,state=_state(values[name]))
                              for name,description in POLICY],
                    total=len(ASSUMPTION_FIELDS),referenced=referenced,unknown=len(unknown),
                    missing_reference_fields=missing,unknown_fields=unknown,
                    reference_ids={key:[entry["evidence_id"] for entry in refs[key]] for key in ASSUMPTION_FIELDS},
                    scenario_sha256=cash["scenario_sha256"],schedule_sha256=timing["schedule_sha256"],
                    independently_verified_count=0,
                    modeled_cash_exposure=None if cash["modeled_cash_exposure"] is None else str(cash["modeled_cash_exposure"]),
                    modeled_expected_net=None if cash["modeled_expected_net"] is None else str(cash["modeled_expected_net"]),
                    modeled_collection_wait_us=wait,source_hold=source_hold,
                    reasons=tuple(dict.fromkeys(reasons)),independently_verified=False,
                    commercial_facts_verified=False,independent_reviewer_authenticated=False,
                    release_eligible=False,execution_eligible=False,external_authority=False)
                result["snapshot_sha256"]=_digest(_json(result))
                validate_snapshot(result)
                self._confirm(profile)
                yield result,task,artifacts
                self._permit()
            self._confirm(profile)

    def inspect(self,plan_id):
        """Fresh local inspection without creating or consuming a Council task."""
        with self._snapshot(plan_id) as (snapshot,_task,_artifacts):
            return snapshot

    def register(self,plan_id):
        """Register one stable task contract for the exact archived saved plan."""
        with self._snapshot(plan_id) as (_snapshot,task,_artifacts):
            with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
                return CouncilCoordinator(store,halt_check=self.halt_check,
                    clock=self.clock).register(task)

    def run_once(self,plan_id):
        """One explicitly requested review of a previously registered plan."""
        with self._snapshot(plan_id) as (snapshot,task,artifacts):
            with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
                result=CouncilCoordinator(store,halt_check=self.halt_check,
                    clock=self.clock).run_once(task,artifacts,audit_snapshot=snapshot)
                return dict(result,snapshot=snapshot)

    def history(self,plan_id):
        """Historical review audit only; never current eligibility or factual verification."""
        self._permit()
        task_id="COUNCIL."+scope_for(plan_id)
        path=self.directory/"council.sqlite3"
        if not path.is_file():
            raise ValueError("Council history unavailable")
        with CouncilAttemptStore(path) as store:
            result=store.audit_history(task_id,halted=False)
        self._permit()
        return result
