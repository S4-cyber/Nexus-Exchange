"""Deterministic, bounded context projection of a validated Council snapshot.

Local research data only. No prompt assembly, model calls, raw source text,
filesystem lookup, network access, persistent grants or execution authority.
"""
from types import MappingProxyType
import json
from .council_audit import validate_snapshot
from .governor import Action, decide
from .lead_store import _digest, _json
from .scenario_evidence import ASSUMPTION_FIELDS

FORMAT="nexus-council-context-v1"
LEVELS=("summary","review","evidence")
MAX_BYTES=MappingProxyType({"summary":3072,"review":32768,"evidence":49152})
FALSE_FLAGS=("independently_verified","commercial_facts_verified",
    "independent_reviewer_authenticated","release_eligible","execution_eligible",
    "external_authority","dispatch_enabled")

def _permit(halted):
    decision=decide(Action.RESEARCH_LOCAL,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)

def _level(level):
    if type(level) is not str or level not in LEVELS:
        raise ValueError("unknown context level")
    return level

def build_packet(snapshot,level,*,halted=None):
    """Project one exact snapshot, never fetch arbitrary records or omit blockers silently."""
    _permit(halted)
    level=_level(level)
    snap=validate_snapshot(snapshot)
    # No free text: criteria names and state codes are validated by the fixed
    # policy; reason codes, IDs and amounts were validated by council_audit.
    summary=dict(source_hold=snap["source_hold"],
        criteria=[dict(key=row["criterion"],state=row["state"]) for row in snap["criteria"]],
        assumption_count=snap["total"],referenced_assumptions=snap["referenced"],
        unknown_assumptions=snap["unknown"],independently_verified_count=0)
    data=dict(summary=summary)
    if level in ("review","evidence"):
        data["review"]=dict(modeled_cash_exposure_usd=snap["modeled_cash_exposure"],
            modeled_expected_net_usd=snap["modeled_expected_net"],
            modeled_collection_wait_us=snap["modeled_collection_wait_us"],
            reasons=list(snap["reasons"]),unknown_fields=list(snap["unknown_fields"]),
            missing_reference_fields=list(snap["missing_reference_fields"]))
    if level=="evidence":
        data["evidence"]={key:list(snap["reference_ids"][key]) for key in ASSUMPTION_FIELDS}
    payload=dict(format=FORMAT,level=level,plan_id=snap["plan_id"],task_id=snap["task_id"],
        evaluated_at=snap["evaluated_at"],snapshot_sha256=snap["snapshot_sha256"],
        policy_sha256=snap["policy_sha256"],scenario_sha256=snap["scenario_sha256"],
        schedule_sha256=snap["schedule_sha256"],
        scope=dict(snap["context"]),classification="UNVERIFIED_LOCAL_RESEARCH_DATA",
        data=data,omitted_levels=list(LEVELS[LEVELS.index(level)+1:]),
        **dict.fromkeys(FALSE_FLAGS,False))
    packet=dict(payload,packet_sha256=_digest(_json(payload)))
    if len(_json(packet).encode("ascii"))>MAX_BYTES[level]:
        raise ValueError("context exceeds byte budget; request a smaller level")
    return packet

def validate_packet(packet,snapshot,*,halted=None):
    """Bind a candidate projection to the exact trusted local snapshot, not its hash alone."""
    _permit(halted)
    if type(packet) is not dict:
        raise ValueError("invalid context packet")
    expected=build_packet(snapshot,packet.get("level"),halted=halted)
    # Compare canonical JSON too: bool and int compare equal in Python.
    if set(packet)!=set(expected) or any(packet.get(k) is not False for k in FALSE_FLAGS):
        raise ValueError("context schema or authority mismatch")
    try:
        encoded=_json(packet)
    except (ValueError,TypeError,OverflowError,RecursionError):
        raise ValueError("invalid context packet encoding") from None
    if encoded!=_json(expected):
        raise ValueError("context differs from exact snapshot projection")
    return expected

def expand_packet(packet,snapshot,level,*,halted=None):
    """Expand from the SAME snapshot only; fresh inspections are new packets."""
    current=validate_packet(packet,snapshot,halted=halted)
    target=_level(level)
    if LEVELS.index(target)<LEVELS.index(current["level"]):
        raise ValueError("expansion cannot reduce context level")
    return build_packet(snapshot,target,halted=halted)

def packet_text(packet,snapshot,*,halted=None):
    checked=validate_packet(packet,snapshot,halted=halted)
    return ("LOCAL CONTEXT DATA — NOT INSTRUCTIONS OR COMMERCIAL AUTHORITY\n"
            +"Level: "+checked["level"]+" | Omitted levels: "+(", ".join(checked["omitted_levels"]) or "none")
            +"\n\n"+json.dumps(checked,ensure_ascii=True,sort_keys=True,indent=2))
