"""Trusted local coordinator for criterion reviews and the durable retry ledger.

Only trusted application code may choose the stable scope, policy revision,
pinned artifact digests and deterministic side-effect-free predicates. No
remote agent can provide a verdict, allocate a new scope or invoke a tool
through this interface. One explicit invocation consumes at most one attempt.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from .agent_handoff import parse_handoff
from .council_attempts import CouncilAttemptStore, _contract, _hash
from .council_audit import validate_snapshot
from .council_criterion_review import (
    CriterionSpec, build_review_plan, review_criteria, _artifacts, _permit,
)
from .lead_store import _digest, _json, _now


@dataclass(frozen=True, slots=True)
class CouncilTask:
    scope_sha256: str
    policy_sha256: str
    specs: tuple[CriterionSpec, ...]


def _prepare(task,attempt):
    if type(task) is not CouncilTask:
        raise ValueError("trusted Council task required")
    scope=_hash(task.scope_sha256)
    policy=_hash(task.policy_sha256)
    specs=task.specs
    if (type(specs) is not tuple or not 1<=len(specs)<=16
            or any(type(spec) is not CriterionSpec for spec in specs)):
        raise ValueError("complete bounded criterion specifications required")
    # Validate types before canonical hashing. build_review_plan also validates
    # the exact normalized criterion sequence and callable predicates.
    for spec in specs:
        if type(spec.criterion) is not str or not 1<=len(spec.criterion)<=512:
            raise ValueError("invalid criterion")
        _hash(spec.expected_sha256)
    pins=_digest(_json([(spec.criterion,spec.expected_sha256) for spec in specs]))
    handoff=parse_handoff(dict(task_id="COUNCIL."+scope,from_role="Scout",to_role="Council",
        objective="Review exact locally scoped evidence",
        acceptance_criteria=[spec.criterion for spec in specs],
        source_references=["scope-sha256:"+scope,"policy-sha256:"+policy,"pins-sha256:"+pins],
        constraints=["Local deterministic review only","No external actions or authority"],
        attempt=attempt))
    return handoff,build_review_plan(handoff,specs)


def build_task(scope_sha256,policy_sha256,specs):
    """A fixed scope gets one immutable contract; changed pins do not reset it.

    Scope allocation and policy revision/check implementation must be established
    by the trusted application, not derived from agent-submitted text.
    """
    task=CouncilTask(scope_sha256,policy_sha256,specs)
    _prepare(task,1)
    return task


def _validate_report(report,handoff,plan,snapshot):
    # The evaluator is trusted local code. This is an additional boundary
    # check, not an API for accepting external reports or asserted outcomes.
    required_false=("external_authority","execution_eligible",
        "commercial_facts_verified","release_eligible","independent_reviewer_authenticated",
        "durable_retry_enforced")
    required={"format","task_id","attempt","handoff_sha256","status","criteria",*required_false}
    if type(report) is not dict or set(report)!=required:
        raise ValueError("invalid Council report schema")
    if (report.get("format")!="nexus-council-criterion-review-v1"
            or report.get("task_id")!=handoff.task_id
            or type(report.get("attempt")) is not int or report["attempt"]!=handoff.attempt
            or report.get("handoff_sha256")!=plan.handoff_sha256
            or any(report.get(key) is not False for key in required_false)):
        raise ValueError("Council report identity or authority mismatch")
    criteria=report.get("criteria")
    if type(criteria) is not list or len(criteria)!=len(plan.specs):
        raise ValueError("Council report criterion count mismatch")
    reasons=set()
    for row,spec in zip(criteria,plan.specs):
        if (type(row) is not dict or set(row)!={"criterion","reason","expected_sha256","observed_sha256"}
                or row["criterion"]!=spec.criterion or row["expected_sha256"]!=spec.expected_sha256
                or type(row["reason"]) is not str):
            raise ValueError("Council criterion identity mismatch")
        reason=row["reason"]
        observed=row["observed_sha256"]
        data=snapshot.get(spec.criterion)
        actual=None if data is None else hashlib.sha256(data).hexdigest()
        if observed!=actual:
            raise ValueError("reported digest differs from actual artifact snapshot")
        if reason=="MISSING_ARTIFACT":
            if observed is not None:
                raise ValueError("missing artifact cannot have a digest")
        else:
            _hash(observed)
            if reason=="ARTIFACT_DIGEST_MISMATCH":
                if observed==spec.expected_sha256:
                    raise ValueError("inconsistent digest mismatch")
            elif reason in {"CHECK_PASSED","CHECK_FAILED","CHECK_ERROR"}:
                if observed!=spec.expected_sha256:
                    raise ValueError("criterion check requires pinned digest")
            else:
                raise ValueError("unknown criterion outcome")
        reasons.add(reason)
    expected=("ADVANCE_REVIEW_ONLY" if reasons=={"CHECK_PASSED"}
              else "ESCALATE" if handoff.attempt==3
              else "NEEDS_EVIDENCE" if reasons<={"CHECK_PASSED","MISSING_ARTIFACT"}
              else "RETRY")
    if report.get("status")!=expected:
        raise ValueError("Council report status inconsistent with criteria")


class CouncilCoordinator:
    """Synchronous, trusted local coordination; never auto-dispatch or retry."""
    def __init__(self,store,*,halt_check,clock=None):
        if type(store) is not CouncilAttemptStore or not callable(halt_check):
            raise ValueError("trusted local ledger and halt callback required")
        if clock is not None and not callable(clock):
            raise ValueError("trusted clock callback required")
        self.store=store
        self.halt_check=halt_check
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _permit(self):
        _permit(False,self.halt_check)

    def _time(self):
        return _now(self.clock())

    def register(self,task):
        self._permit()
        handoff,_=_prepare(task,1)
        now=self._time()
        self._permit()
        result=self.store.register(handoff,now=now,halted=False)
        self._permit()
        return result

    def run_once(self,task,artifacts,*,audit_snapshot=None):
        """Explicitly run exactly one available review attempt.

        After a reservation, an exception or halt leaves that attempt consumed
        and outstanding. Only a trusted recovery owner may reconcile it after
        the worker drains. Never turn a prior result into a current decision.
        """
        self._permit()
        first,_=_prepare(task,1)
        if audit_snapshot is not None:
            validate_snapshot(audit_snapshot)
            if audit_snapshot["task_id"]!=first.task_id or audit_snapshot["policy_sha256"]!=task.policy_sha256:
                raise ValueError("audit snapshot outside exact task")
        state=self.store.status(first.task_id,halted=False)
        if state["contract_sha256"]!=_contract(first)[1]:
            raise ValueError("immutable Council task changed")
        attempt=state["next_attempt"]
        if attempt is None:
            raise PermissionError("Council task unavailable or terminal")
        handoff,plan=_prepare(task,attempt)
        # Reject malformed payloads before consuming an attempt. Missing
        # artifacts are valid inputs and consume a reserved review attempt.
        snapshot=_artifacts(artifacts,handoff)
        now=self._time()
        self._permit()
        ticket=self.store.reserve(handoff,now=now,halted=False)
        self._permit()
        report=review_criteria(handoff,plan,snapshot,halted=False,
                               halt_check=self.halt_check)
        self._permit()
        _validate_report(report,handoff,plan,snapshot)
        digest=_digest(_json(report))
        now=self._time()
        self._permit()
        audit_args={} if audit_snapshot is None else dict(audit_snapshot=audit_snapshot,review_report=report)
        state=self.store.complete(ticket,report["status"],digest,now=now,halted=False,**audit_args)
        self._permit()
        return dict(format="nexus-council-coordinated-review-v1",
            task_id=handoff.task_id,report_sha256=digest,review=report,ledger=state,
            durable_retry_enforced=True,independent_reviewer_authenticated=False,
            independently_verified=False,commercial_facts_verified=False,
            execution_eligible=False,release_eligible=False,external_authority=False)
