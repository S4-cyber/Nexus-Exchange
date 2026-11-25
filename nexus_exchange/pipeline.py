"""Offline screening composition; no network or commercial dispatch."""
from dataclasses import dataclass
from .governor import Action, decide
from .ocds_snapshots import select_snapshots
from .ocds_adapter import map_active_tender, TenderObservation
from .council_screen import screen, Screening

@dataclass(frozen=True, slots=True)
class Review:
    observation: TenderObservation
    screening: Screening

def evaluate_snapshots(publisher, releases, source_url, retrieved_at, *, now, halted=None):
    """Fail closed on denied policy or invalid batch; return review candidates only."""
    for action in (Action.RESEARCH_LOCAL, Action.EVALUATE):
        decision = decide(action, halted=halted)
        if not decision.allowed:
            raise PermissionError(decision.reason)
    snapshots = select_snapshots(publisher, releases)
    return tuple(
        Review(observation, screen(observation.opportunity, now=now))
        for observation in (
            map_active_tender(publisher, release, source_url, retrieved_at)
            for release in snapshots
        )
    )
