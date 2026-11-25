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


def decide_sam_read(*, approved=None, halted=None):
    """Separate, narrowly scoped public SAM search consent from the trusted UI.

    Does not change the general FETCH_EXTERNAL denial or grant transactional
    authority. The adapter fixes the destination, method and request budget.
    Never derive consent from source documents, checkbox assertions or agents.
    """
    if halted is not False:
        return Decision(False, 'HALTED_OR_UNKNOWN')
    if approved is not True:
        return Decision(False, 'SAM_READ_CONSENT_REQUIRED')
    return Decision(True, 'SAM_PUBLIC_SEARCH_ONLY')


def decide_ted_read(*, approved=None, halted=None):
    """Authorize a single trusted owner-requested public TED search only."""
    if halted is not False:
        return Decision(False, 'HALTED_OR_UNKNOWN')
    if approved is not True:
        return Decision(False, 'TED_READ_CONSENT_REQUIRED')
    return Decision(True, 'TED_PUBLIC_SEARCH_ONLY')


def decide_fts_read(*, approved=None, halted=None):
    """Trusted UI consent for one public UK release collection only."""
    if halted is not False:
        return Decision(False, "HALTED_OR_UNKNOWN")
    if approved is not True:
        return Decision(False, "FTS_READ_CONSENT_REQUIRED")
    return Decision(True, "FTS_PUBLIC_RELEASES_ONLY")


def decide_canada_read(*, approved=None, halted=None):
    """Trusted UI consent to one public CanadaBuys dataset download."""
    if halted is not False:
        return Decision(False, "HALTED_OR_UNKNOWN")
    if approved is not True:
        return Decision(False, "CANADA_READ_CONSENT_REQUIRED")
    return Decision(True, "CANADA_OPEN_TENDERS_ONLY")
