"""Per-plan cost-adjusted hypothetical cash flow and allocation.

All cost values remain owner assumptions. No accounting, actual cash, transfers,
withdrawals, payment provider, or authorization to reinvest.
"""
import re

from .cash_feasibility import COSTS
from .checklist_store import _hash
from .digital_deliverable import _permit
from .finance_workspace import aging, usd, validate_record
from .lead_store import _digest, _json
from .scenario_store import _inputs
from .scout import _timestamp
from .simulated_receivables import MAX_CENTS, _FLAGS, _cents

FORMAT="nexus-simulated-cashflow-v1"
_FLAGS_EXTRA=tuple(dict.fromkeys((*_FLAGS,"costs_verified","allocation_saved",
                                 "portfolio_aggregation","actual_cashflow_verified")))


def _reserve(value):
    if type(value) is not int or not 0<=value<=10000:
        raise ValueError("reserve share must be integer basis points 0–10000")
    return value


def parse_reserve(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,5}",value):
        raise ValueError("enter explicit reserve share in basis points")
    return _reserve(int(value))


def _cost(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?",value):
        raise ValueError("invalid modeled cost")
    whole,_,fraction=value.partition(".")
    return int(whole)*100+int(fraction.ljust(2,"0") or "0")


def _compute(record,obligation,costs,*,as_of,reserve_bps):
    """Recompute a projection from bounded cents and validated ledger identities."""
    bps=_reserve(reserve_bps)
    if type(costs) is not dict or set(costs)!=set(COSTS) or any(
            v is not None and (type(v) is not int or not 0<=v<=MAX_CENTS)
            for v in costs.values()):
        raise ValueError("all seven bounded modeled cost categories required")
    a=aging(record,obligation,as_of)
    invoice=record["invoice"]
    unknown=[key for key in COSTS if costs[key] is None]
    known=sum(costs[key] for key in COSTS if costs[key] is not None)
    total=None if unknown else known
    issued=a["status"]!="SIM_NOT_YET_ISSUED"
    # Conservative allocation: reserve ALL scenario costs from assumed issue
    # onward. Before issue we have no modeled dates for these outlays, so no
    # as-of net estimate is presented. Costs are not actual expenses.
    received=a["simulated_received_as_of_cents"]
    net=None if total is None or not issued else received-total
    full_net=None if total is None else invoice["gross_cents"]-total
    reasons=[]
    if not issued:
        reasons.append("PREISSUE_COST_TIMING_UNRESOLVED")
    if unknown:
        reasons.append("MODELED_COSTS_UNKNOWN")
    if a["evidence_changed"]:
        reasons.append("OBLIGATION_EVIDENCE_CHANGED")
    if a["status"]!="SIM_SETTLED_AS_OF":
        reasons.append("MODEL_NOT_FULLY_SETTLED_AS_OF")
    if net is not None and net<=0:
        reasons.append("NO_POSITIVE_MODELED_SURPLUS")
    allocation=not reasons
    # Ceiling reserve in cents, never round away the protected portion.
    reserve=(net*bps+9999)//10000 if allocation else None
    reinvestment=net-reserve if allocation else None
    payload=dict(format=FORMAT,mode="SIMULATION_ONLY",currency="USD",
        plan_id=invoice["plan_id"],invoice_id=invoice["invoice_id"],
        scenario_sha256=invoice["scenario_sha256"],receipt_head_sha256=record["head_sha256"],
        obligation_head_sha256=obligation["head_sha256"],aging_sha256=a["projection_sha256"],
        as_of=as_of,reserve_bps=bps,
        modeled_costs_cents={k:costs[k] for k in COSTS},unknown_cost_categories=unknown,
        known_cost_subtotal_cents=known,modeled_total_cost_cents=total,
        modeled_full_collection_net_cents=full_net,simulated_received_as_of_cents=received,
        simulated_outstanding_as_of_cents=a["simulated_outstanding_as_of_cents"],
        future_dated_receipts_cents=a["future_dated_receipts_cents"],
        modeled_net_as_of_cents=net,modeled_cost_shortfall_cents=None if net is None else max(0,-net),
        allocation_modeled=allocation,modeled_protected_reserve_cents=reserve,
        modeled_reinvestment_cents=reinvestment,reasons=reasons,
        cost_timing_assumption="ALL_DECLARED_COSTS_RESERVED_FROM_ASSUMED_ISSUE",
        **dict.fromkeys(_FLAGS_EXTRA,False))
    return dict(payload,projection_sha256=_digest(_json(payload)))


def project_cashflow(record,obligation,saved,*,as_of,reserve_bps,halted=None,halt_check=None):
    """Resolve all cost assumptions from the exact historical saved plan."""
    _permit(halted,halt_check)
    bps=_reserve(reserve_bps)
    if type(saved) is not dict:
        raise ValueError("saved scenario unavailable")
    plan_id=_hash(saved.get("plan_id"))
    checked=validate_record(record,plan_id,obligation)
    invoice=checked["invoice"]
    inputs=_inputs(saved["context"],saved["scenario"],saved["plan"])
    scenario=inputs["scenario"]
    digest=_digest(_json(dict(context=inputs["context"],scenario=scenario)))
    if (_digest(_json(inputs))!=plan_id or digest!=invoice["scenario_sha256"]
            or inputs["context"]!=obligation["binding"]["contract"]["context"]
            or _cents(scenario["compensation"])!=invoice["gross_cents"]
            or scenario["payment_days_after_delivery"]!=invoice["payment_days"]
            or _timestamp(saved["created_at"])>_timestamp(obligation["created_at"])
            or any(saved.get(k) is not False for k in (
                "independently_verified","execution_eligible","external_authority","genesis_verified"))):
        raise ValueError("cash-flow scenario scope mismatch")
    result=_compute(checked,obligation,{key:_cost(scenario["costs"][key]) for key in COSTS},
                    as_of=as_of,reserve_bps=bps)
    _permit(halted,halt_check)
    return result


def validate_projection(raw,record,obligation,*,as_of,reserve_bps):
    """UI consistency check, not independent verification of cost assumptions."""
    if type(raw) is not dict:
        raise ValueError("invalid cash-flow projection")
    expected=_compute(record,obligation,raw.get("modeled_costs_cents"),
                      as_of=as_of,reserve_bps=reserve_bps)
    if _json(raw)!=_json(expected):
        raise ValueError("cash-flow projection or authority mismatch")
    return expected


def projection_text(report):
    def amount(value):
        if value is None:
            return "Unresolved"
        return ("-" if value<0 else "")+usd(abs(value))
    lines=["SIMULATION ONLY — no spendable funds or realized revenue",
        "Model date: "+report["as_of"],
        "Assumption: all declared costs reserved from assumed issue; actual expense timing unknown.",
        "Known cost subtotal: "+amount(report["known_cost_subtotal_cents"]),
        "Total modeled costs: "+amount(report["modeled_total_cost_cents"]),
        "Modeled net if fully collected: "+amount(report["modeled_full_collection_net_cents"]),
        "Cost-adjusted modeled net as of date: "+amount(report["modeled_net_as_of_cents"]),
        "Modeled cost shortfall: "+amount(report["modeled_cost_shortfall_cents"]),
        "Reserve share: "+str(report["reserve_bps"])+" bp (100 bp = 1%)",
        "Hypothetical protected reserve: "+amount(report["modeled_protected_reserve_cents"]),
        "Hypothetical reinvestment: "+amount(report["modeled_reinvestment_cents"]),
        "Allocation: "+("Modeled only" if report["allocation_modeled"] else "Held"),
        "Reasons: "+(", ".join(report["reasons"]) or "Local model criteria met only"),
        "Unknown costs: "+(", ".join(report["unknown_cost_categories"]) or "None in declared assumptions"),
        "Projection fingerprint: "+report["projection_sha256"]]
    return "\n".join(lines)
