"""Bounded, historical Council scenario audit schema. Not authorization.

Canonical digests provide local integrity and association checks, not a
signature, source authentication, or protection from an adversarial owner
who can rewrite all database records and their digests.
"""
from dataclasses import fields
from decimal import Decimal
import re

from .agent_handoff import AgentHandoff, MAX_ATTEMPTS, parse_handoff
from .checklist_store import _context, _hash
from .lead_store import _digest, _json
from .scenario_evidence import ASSUMPTION_FIELDS, MAX_REFERENCES_PER_FIELD
from .schedule_feasibility import _iso
from .scout import _timestamp

POLICY=(
    ("source_and_capability","Historical source and declared profile suitability, not verified eligibility"),
    ("financial_model","Known modeled budget fit and strictly positive expected net"),
    ("delivery_schedule","Modeled preparation, delivery and declared labor fit"),
    ("collection_timing","Known nonnegative modeled wait until payment"),
    ("reference_coverage","Every known assumption has a recorded reference; no factual verification"),
)
POLICY_SHA256=_digest(_json(dict(namespace="scenario-local-review-v1",criteria=POLICY)))
MAX_AUDIT_BYTES=65536
_FALSE_FLAGS={"independently_verified","commercial_facts_verified","independent_reviewer_authenticated",
              "release_eligible","execution_eligible","external_authority"}
_SNAPSHOT_FIELDS={"format","plan_id","context","evaluated_at","task_id","policy_sha256","criteria",
    "total","referenced","unknown","missing_reference_fields","unknown_fields",
    "independently_verified_count","modeled_cash_exposure","modeled_expected_net",
    "modeled_collection_wait_us","source_hold","reasons","snapshot_sha256",
    "reference_ids","scenario_sha256","schedule_sha256"}|_FALSE_FLAGS
_REVIEW_FALSE={"external_authority","execution_eligible","commercial_facts_verified",
               "release_eligible","independent_reviewer_authenticated","durable_retry_enforced"}
_REVIEW_FIELDS={"format","task_id","attempt","handoff_sha256","status","criteria"}|_REVIEW_FALSE
_AUDIT_FIELDS={"version","task_id","attempt","contract_sha256","reservation_id",
               "completed_at","report_sha256","snapshot","review"}
_STATES={"LOCAL_CHECK_FITS","LOCAL_CHECK_FAILS","UNRESOLVED"}
_HOLDS={"SOURCE_REVIEW_REQUIRED","CONTRACTOR_INTELLIGENCE_ONLY","SOURCE_NOT_SELECTED"}
_CODE=re.compile(r"[A-Z][A-Z0-9_]{0,95}")
_AMOUNT=re.compile(r"-?[0-9]{1,15}(?:\.[0-9]{1,16})?(?:E[+-][0-9]{1,2})?")


def scope_for(plan_id):
    return _digest(_json(dict(namespace="scenario-local-review",plan_id=_hash(plan_id))))


def _stamp(value):
    if type(value) is not str:
        raise ValueError("canonical audit time required")
    stamp=_timestamp(value)
    if _iso(stamp)!=value:
        raise ValueError("noncanonical audit time")
    return stamp


def _amount(value,*,nonnegative=False):
    if value is None:
        return
    if type(value) is not str or _AMOUNT.fullmatch(value) is None:
        raise ValueError("invalid modeled audit amount")
    number=Decimal(value)
    if (not number.is_finite() or str(number)!=value or number.copy_abs()>Decimal("1e14")
            or not -16<=number.as_tuple().exponent<=14 or (nonnegative and number<0)):
        raise ValueError("invalid modeled audit amount")


def _field_list(value):
    if (type(value) is not list or any(type(k) is not str or k not in ASSUMPTION_FIELDS for k in value)
            or value!=[key for key in ASSUMPTION_FIELDS if key in value]):
        raise ValueError("invalid ordered assumption fields")
    return value


def _reason(value):
    if type(value) is not str:
        return False
    if _CODE.fullmatch(value):
        return True
    for prefix in ("REFERENCE_REQUIRED:","ASSUMPTION_UNKNOWN:"):
        if value.startswith(prefix) and value[len(prefix):] in ASSUMPTION_FIELDS:
            return True
    return value.startswith("COST_UNKNOWN:") and "cost:"+value[len("COST_UNKNOWN:"):] in ASSUMPTION_FIELDS


def validate_snapshot(snapshot):
    """Strict fixed-policy report shape; never persist arbitrary text or paths."""
    if type(snapshot) is not dict or set(snapshot)!=_SNAPSHOT_FIELDS:
        raise ValueError("invalid Council snapshot schema")
    plan_id=_hash(snapshot["plan_id"])
    context=_context(snapshot["context"])
    if (context!=snapshot["context"] or context["profile_revision"] is None
            or snapshot["format"]!="nexus-scout-local-council-snapshot-v1"
            or snapshot["task_id"]!="COUNCIL."+scope_for(plan_id)
            or snapshot["policy_sha256"]!=POLICY_SHA256
            or any(snapshot[key] is not False for key in _FALSE_FLAGS)):
        raise ValueError("invalid Council snapshot identity or authority")
    if _stamp(snapshot["evaluated_at"])<_stamp(context["retrieved_at"]):
        raise ValueError("snapshot predates archived observation")
    for key in ("scenario_sha256","schedule_sha256","snapshot_sha256"):
        _hash(snapshot[key])
    if _digest(_json({k:v for k,v in snapshot.items() if k!="snapshot_sha256"}))!=snapshot["snapshot_sha256"]:
        raise ValueError("snapshot fingerprint mismatch")
    missing=_field_list(snapshot["missing_reference_fields"])
    unknown=_field_list(snapshot["unknown_fields"])
    refs=snapshot["reference_ids"]
    if type(refs) is not dict or set(refs)!=set(ASSUMPTION_FIELDS):
        raise ValueError("invalid assumption reference identities")
    ids=[]
    for key in ASSUMPTION_FIELDS:
        row=refs[key]
        if type(row) is not list or len(row)>MAX_REFERENCES_PER_FIELD:
            raise ValueError("invalid assumption reference count")
        ids.extend(_hash(value) for value in row)
    if (len(set(ids))!=len(ids) or missing!=[key for key in ASSUMPTION_FIELDS if not refs[key]]
            or any(key not in missing for key in unknown)):
        raise ValueError("inconsistent assumption reference identities")
    counts={"total":len(ASSUMPTION_FIELDS),"referenced":len(ASSUMPTION_FIELDS)-len(missing),
            "unknown":len(unknown),"independently_verified_count":0}
    if any(type(snapshot[k]) is not int or snapshot[k]!=v for k,v in counts.items()):
        raise ValueError("inconsistent Council coverage counts")
    criteria=snapshot["criteria"]
    if type(criteria) is not list or len(criteria)!=len(POLICY):
        raise ValueError("invalid Council policy criteria")
    states={}
    for row,(name,description) in zip(criteria,POLICY):
        if (type(row) is not dict or set(row)!={"criterion","description","state"}
                or row["criterion"]!=name or row["description"]!=description
                or type(row["state"]) is not str or row["state"] not in _STATES):
            raise ValueError("invalid Council criterion state")
        states[name]=row["state"]
    if states["reference_coverage"]!=("UNRESOLVED" if missing or unknown else "LOCAL_CHECK_FITS"):
        raise ValueError("inconsistent reference coverage verdict")
    hold=snapshot["source_hold"]
    if hold is not None and (type(hold) is not str or hold not in _HOLDS):
        raise ValueError("invalid source hold")
    if states["source_and_capability"]!=("LOCAL_CHECK_FITS" if hold is None else "LOCAL_CHECK_FAILS"):
        raise ValueError("inconsistent source hold verdict")
    wait=snapshot["modeled_collection_wait_us"]
    if wait is not None and (type(wait) is not int or abs(wait)>4*10**17):
        raise ValueError("invalid modeled collection wait")
    if states["collection_timing"]!=("UNRESOLVED" if wait is None else
            "LOCAL_CHECK_FITS" if wait>=0 else "LOCAL_CHECK_FAILS"):
        raise ValueError("inconsistent collection verdict")
    _amount(snapshot["modeled_cash_exposure"],nonnegative=True)
    _amount(snapshot["modeled_expected_net"])
    reasons=snapshot["reasons"]
    if (type(reasons) not in (tuple,list) or not 1<=len(reasons)<=256
            or any(not _reason(reason) for reason in reasons) or len(set(reasons))!=len(reasons)):
        raise ValueError("invalid bounded reason codes")
    return snapshot


def _validate_review(snapshot,review,record,entry):
    if type(review) is not dict or set(review)!=_REVIEW_FIELDS:
        raise ValueError("invalid historical criterion review schema")
    if (review["format"]!="nexus-council-criterion-review-v1"
            or review["task_id"]!=record["task_id"]
            or type(review["attempt"]) is not int or review["attempt"]!=entry["attempt"]
            or review["status"]!=entry["outcome"]
            or any(review[key] is not False for key in _REVIEW_FALSE)
            or _digest(_json(review))!=entry["report_sha256"]):
        raise ValueError("historical review identity or outcome mismatch")
    rows=review["criteria"]
    if type(rows) is not list or len(rows)!=len(POLICY):
        raise ValueError("invalid historical criterion count")
    pins=[]
    reasons=set()
    expected_reason={"LOCAL_CHECK_FITS":"CHECK_PASSED","LOCAL_CHECK_FAILS":"CHECK_FAILED",
                     "UNRESOLVED":"MISSING_ARTIFACT"}
    for row,criterion in zip(rows,snapshot["criteria"]):
        if (type(row) is not dict or set(row)!={"criterion","reason","expected_sha256","observed_sha256"}
                or row["criterion"]!=criterion["criterion"]
                or row["reason"]!=expected_reason[criterion["state"]]):
            raise ValueError("historical criterion differs from snapshot")
        expected=_hash(row["expected_sha256"])
        if row["observed_sha256"]!=(None if row["reason"]=="MISSING_ARTIFACT" else expected):
            raise ValueError("historical artifact digest mismatch")
        pins.append((row["criterion"],expected))
        reasons.add(row["reason"])
    expected_status=("ADVANCE_REVIEW_ONLY" if reasons=={"CHECK_PASSED"}
                     else "ESCALATE" if entry["attempt"]==MAX_ATTEMPTS
                     else "NEEDS_EVIDENCE" if reasons<={"CHECK_PASSED","MISSING_ARTIFACT"}
                     else "RETRY")
    if review["status"]!=expected_status:
        raise ValueError("historical review status inconsistent with checks")
    scope=scope_for(snapshot["plan_id"])
    handoff=parse_handoff(dict(task_id=record["task_id"],from_role="Scout",to_role="Council",
        objective="Review exact locally scoped evidence",
        acceptance_criteria=[name for name,_ in POLICY],
        source_references=["scope-sha256:"+scope,"policy-sha256:"+POLICY_SHA256,
                           "pins-sha256:"+_digest(_json(pins))],
        constraints=["Local deterministic review only","No external actions or authority"],
        attempt=entry["attempt"]))
    raw={field.name:getattr(handoff,field.name) for field in fields(AgentHandoff)}
    if (_digest(_json(raw))!=_hash(review["handoff_sha256"])
            or _digest(_json({k:v for k,v in raw.items() if k!="attempt"}))!=record["contract_sha256"]):
        raise ValueError("historical handoff contract mismatch")


def validate_audit(audit,record,entry):
    if type(audit) is not dict or set(audit)!=_AUDIT_FIELDS or type(audit["version"]) is not int or audit["version"]!=1:
        raise ValueError("invalid Council audit schema")
    bindings={"task_id":record["task_id"],"contract_sha256":record["contract_sha256"],
        "attempt":entry["attempt"],"reservation_id":entry["reservation_id"],
        "completed_at":entry["completed_at"],"report_sha256":entry["report_sha256"]}
    if any(audit[k]!=v for k,v in bindings.items()) or type(audit["attempt"]) is not int:
        raise ValueError("Council audit ledger binding mismatch")
    snapshot=validate_snapshot(audit["snapshot"])
    if snapshot["task_id"]!=record["task_id"] or _stamp(snapshot["evaluated_at"])>_stamp(entry["reserved_at"]):
        raise ValueError("Council audit snapshot scope or time mismatch")
    _validate_review(snapshot,audit["review"],record,entry)
    if len(_json(audit))>MAX_AUDIT_BYTES:
        raise ValueError("Council audit exceeds payload capacity")
    return audit


def build_audit(record,entry,snapshot,review):
    return validate_audit(dict(version=1,task_id=record["task_id"],attempt=entry["attempt"],
        contract_sha256=record["contract_sha256"],reservation_id=entry["reservation_id"],
        completed_at=entry["completed_at"],report_sha256=entry["report_sha256"],
        snapshot=snapshot,review=review),record,entry)
