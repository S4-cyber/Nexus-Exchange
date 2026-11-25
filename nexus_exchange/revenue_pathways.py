"""Review-only revenue routing. No bank, network, account or submission authority."""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from .governor import Action, decide

class Mode(str, Enum):
    GENESIS = "Genesis — zero capital"
    CATALYST = "Catalyst — funded planning"

@dataclass(frozen=True, slots=True)
class Source:
    key: str
    title: str
    url: str
    kind: str
    prerequisites: tuple[str,...]

SOURCES = (
    Source("sam","SAM.gov contracts","https://sam.gov/opportunities","earned",
        ("Create or sign in to your own Login.gov/SAM account when needed.",
         "Confirm entity registration/UEI and active status if required for the award.",
         "Check set-asides, NAICS, solicitation instructions and contract clauses.",
         "Obtain a public API key in SAM account settings for future authorized search.")),
    Source("subnet","SBA SUBNet","https://legacy.sba.gov/federal-contracting/contracting-guide/prime-subcontracting/subcontracting-opportunities","earned",
        ("Confirm the prime contractor, subcontract terms and required qualifications.",
         "Verify actual delivery capacity and the prime's consent/communication channel.")),
    Source("grants","Grants.gov","https://www.grants.gov/","restricted_funding",
        ("Confirm applicant category, notice eligibility and allowed use of funds.",
         "Verify organization registration and authorized representative where applicable.",
         "Separate restricted grant funding from earned commercial revenue.")),
)
SOURCE_MAP = {source.key:source for source in SOURCES}
CHECKS = (
    ("source","Verify original notice, issuer, current status and deadline."),
    ("profile","Confirm owner/entity identity, account and actual platform eligibility."),
    ("capability","Verify scope, lawful delivery capability and available resources."),
    ("permission","Check automation, AI use, subcontracting and submission rules."),
    ("payment","Verify written compensation, payer, acceptance criteria and payment timing."),
    ("cost","Document all cash costs and maximum pre-payment cash exposure."),
    ("authorization","Owner reviews the exact proposed action; obtain required authority separately."),
)

@dataclass(frozen=True, slots=True)
class Task:
    key: str
    instruction: str
    status: str

@dataclass(frozen=True, slots=True)
class Plan:
    mode: Mode
    source: Source
    budget: Decimal
    exposure: Decimal | None
    tasks: tuple[Task,...]
    reasons: tuple[str,...]
    ready_for_review: bool
    external_authority: bool = False

def _money(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?", value):
        raise ValueError("enter nonnegative USD amount with up to two decimal places")
    return Decimal(value)

def source_url(key):
    if type(key) is not str or key not in SOURCE_MAP:
        raise ValueError("unknown approved source")
    return SOURCE_MAP[key].url

def plan_lead(mode,source_key,*,budget="0",exposure=None,confirmed=(),halted=None):
    """Confirmed denotes caller-supplied checklist assertions, not verified proof."""
    decision = decide(Action.EVALUATE,halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    if type(mode) is not Mode:
        raise ValueError("choose operating pathway")
    source_url(source_key)
    source = SOURCE_MAP[source_key]
    budget = _money(budget)
    exposure = None if exposure is None else _money(exposure)
    if mode is Mode.GENESIS and budget != 0:
        raise ValueError("Genesis budget must be zero")
    if type(confirmed) not in (tuple,list) or len(confirmed)>len(CHECKS):
        raise ValueError("invalid checklist assertions")
    known = {key for key,_ in CHECKS}
    if any(type(key) is not str or key not in known for key in confirmed) or len(set(confirmed))!=len(confirmed):
        raise ValueError("invalid checklist key")
    tasks = tuple(Task(key,text,"asserted; verification required" if key in confirmed else "needs action")
                  for key,text in CHECKS)
    reasons = []
    if source.kind != "earned":
        reasons.append("RESTRICTED_FUNDING_NOT_REVENUE")
    if exposure is None:
        reasons.append("CASH_EXPOSURE_UNKNOWN")
    elif exposure > budget:
        reasons.append("EXPOSURE_EXCEEDS_BUDGET")
    if any(key not in confirmed for key,_ in CHECKS):
        reasons.append("CHECKLIST_INCOMPLETE")
    # Even a fully asserted checklist is a proposal for independent review.
    return Plan(mode,source,budget,exposure,tasks,tuple(reasons),not reasons)
