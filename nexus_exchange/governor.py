"""Pure fail-closed policy for offline Exchange research, not runtime authority."""
from dataclasses import dataclass
from enum import Enum


class Action(Enum):
    RESEARCH_LOCAL = 'research_local'
    EVALUATE = 'evaluate'
    DRAFT = 'draft'
    SIMULATE = 'simulate'
    FETCH_EXTERNAL = 'fetch_external'
    OUTREACH = 'outreach'
    BID = 'bid'
    SIGNATURE = 'signature'
    CONTRACT = 'contract'
    PAYMENT = 'payment'
    BROKERAGE = 'brokerage'
    CUSTODY = 'custody'
    INVENTORY = 'inventory'


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str
    external_authority: bool = False


_LOCAL = frozenset({Action.RESEARCH_LOCAL, Action.EVALUATE, Action.DRAFT, Action.SIMULATE})


def decide(action, *, halted=None):
    """Only a trusted caller may supply halt state; unknown state denies all.

    No external authorization can be granted by this offline policy. A local
    allow is not permission to dispatch network, payment or document tools.
    """
    if halted is not False:
        return Decision(False, 'HALTED_OR_UNKNOWN')
    if type(action) is not Action:
        return Decision(False, 'UNKNOWN_ACTION')
    if action not in _LOCAL:
        return Decision(False, 'EXTERNAL_ACTION_DISABLED')
    return Decision(True, 'OFFLINE_ONLY')
