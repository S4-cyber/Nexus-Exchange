"""Criterion-bound local Council review; no agent-controlled execution or authority.

Only trusted in-process application code may construct the review plan, pin
artifact digests from an independent source, and supply bounded, deterministic
predicates. Untrusted agent messages cannot select predicates, paths, tools or
expected digests. A digest match alone cannot pass a criterion. This module
does not authenticate reviewers, verify commercial facts, or persist retries.
"""
from dataclasses import dataclass, fields
import hashlib
import hmac
import json
import re
from typing import Callable

from .agent_handoff import AgentHandoff, MAX_ATTEMPTS, parse_handoff
from .governor import Action, decide

MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 4 * MAX_ARTIFACT_BYTES
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CriterionSpec:
    criterion: str
    expected_sha256: str
    check: Callable[[bytes], bool]


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    handoff_sha256: str
    specs: tuple[CriterionSpec, ...]


def _handoff(handoff):
    if type(handoff) is not AgentHandoff:
        raise ValueError("normalized handoff required")
    # Revalidate even manually constructed dataclasses; avoid deep-copy hooks
    # on arbitrary nested objects before strict validation.
    return parse_handoff({f.name: getattr(handoff, f.name) for f in fields(AgentHandoff)})


def _handoff_digest(handoff):
    raw = {f.name: getattr(handoff, f.name) for f in fields(AgentHandoff)}
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _validate_specs(handoff, specs):
    if type(specs) is not tuple or len(specs) != len(handoff.acceptance_criteria):
        raise ValueError("complete trusted criterion tuple required")
    for criterion, spec in zip(handoff.acceptance_criteria, specs):
        if (type(spec) is not CriterionSpec or type(spec.criterion) is not str
                or spec.criterion != criterion
                or type(spec.expected_sha256) is not str
                or _SHA256.fullmatch(spec.expected_sha256) is None
                or not callable(spec.check)):
            raise ValueError("invalid trusted criterion specification")
    return specs


def build_review_plan(handoff, specs):
    """Bind trusted code-supplied checks to the complete normalized handoff.

    Never deserialize a plan or construct its pins from the agent's proposed
    evidence or verdict. The caller must establish the independent trust root.
    """
    handoff = _handoff(handoff)
    return ReviewPlan(_handoff_digest(handoff), _validate_specs(handoff, specs))


def _permit(halted, halt_check):
    if halted is not False:
        raise PermissionError("HALTED_OR_UNKNOWN")
    if halt_check is not None:
        if not callable(halt_check):
            raise PermissionError("HALTED_OR_UNKNOWN")
        try:
            live = halt_check()
        except Exception:
            raise PermissionError("HALTED_OR_UNKNOWN") from None
    else:
        live = False
    if not decide(Action.EVALUATE, halted=live).allowed:
        raise PermissionError("HALTED_OR_UNKNOWN")


def _artifacts(raw, handoff):
    if type(raw) is not dict or len(raw) > len(handoff.acceptance_criteria):
        raise ValueError("invalid bounded artifact mapping")
    allowed = set(handoff.acceptance_criteria)
    total = 0
    # Validate the entire input before invoking any trusted predicate.
    snapshot = {}
    for key, data in raw.items():
        if type(key) is not str or key not in allowed:
            raise ValueError("artifact outside exact criterion set")
        if type(data) is not bytes or not 1 <= len(data) <= MAX_ARTIFACT_BYTES:
            raise ValueError("invalid bounded artifact bytes")
        total += len(data)
        if total > MAX_TOTAL_ARTIFACT_BYTES:
            raise ValueError("aggregate artifact capacity exceeded")
        snapshot[key] = data
    return snapshot


def review_criteria(handoff, plan, artifacts, *, halted=None, halt_check=None):
    """Recompute each criterion over a pinned immutable byte artifact.

    The plan and predicates are trusted in-process objects, not agent inputs.
    Predicates must be local, deterministic, bounded, and free of side effects.
    No file/network/tool access is implemented here. All output remains
    review-only; even successful checks establish neither commercial truth nor
    release readiness. The attempt counter is not a durable retry ledger.
    """
    _permit(halted, halt_check)
    handoff = _handoff(handoff)
    if (type(plan) is not ReviewPlan or type(plan.handoff_sha256) is not str
            or _SHA256.fullmatch(plan.handoff_sha256) is None):
        raise ValueError("trusted review plan required")
    expected = _handoff_digest(handoff)
    if not hmac.compare_digest(plan.handoff_sha256, expected):
        raise ValueError("review plan outside exact handoff")
    specs = _validate_specs(handoff, plan.specs)
    snapshot = _artifacts(artifacts, handoff)
    results = []
    for spec in specs:
        _permit(halted, halt_check)
        data = snapshot.get(spec.criterion)
        observed = None
        if data is None:
            reason = "MISSING_ARTIFACT"
        else:
            observed = hashlib.sha256(data).hexdigest()
            if not hmac.compare_digest(observed, spec.expected_sha256):
                reason = "ARTIFACT_DIGEST_MISMATCH"
            else:
                _permit(halted, halt_check)
                try:
                    reason = "CHECK_PASSED" if spec.check(data) is True else "CHECK_FAILED"
                except Exception:
                    reason = "CHECK_ERROR"
        _permit(halted, halt_check)
        results.append(dict(criterion=spec.criterion,reason=reason,
                            expected_sha256=spec.expected_sha256,observed_sha256=observed))
    reasons = {row["reason"] for row in results}
    if reasons == {"CHECK_PASSED"}:
        status = "ADVANCE_REVIEW_ONLY"
    elif handoff.attempt == MAX_ATTEMPTS:
        status = "ESCALATE"
    elif reasons <= {"CHECK_PASSED", "MISSING_ARTIFACT"}:
        status = "NEEDS_EVIDENCE"
    else:
        status = "RETRY"
    _permit(halted, halt_check)
    return dict(format="nexus-council-criterion-review-v1",task_id=handoff.task_id,
                attempt=handoff.attempt,handoff_sha256=expected,status=status,criteria=results,
                external_authority=False,execution_eligible=False,commercial_facts_verified=False,
                release_eligible=False,independent_reviewer_authenticated=False,
                durable_retry_enforced=False)
