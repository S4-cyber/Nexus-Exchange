"""Offline dashboard projection from ordered task events; no execution authority."""
from dataclasses import dataclass
from .scout import _text, _timestamp
from .dashboard_tasks import task_page

@dataclass(frozen=True, slots=True)
class TaskState:
    task_id: str
    target: str
    state: str
    timestamp: str

_TRANSITIONS = {None: {"queued"}, "queued": {"running", "cancelled", "interrupted"},
                "running": {"succeeded", "failed", "cancelled", "interrupted"}}

def project(events, page=1):
    states = {}
    history = []
    previous_time = None
    for event in events:
        if type(event) is not dict or set(event) != {"task_id","target","state","timestamp"}:
            raise ValueError("invalid event")
        task = _text(event["task_id"],128)
        target = _text(event["target"],256)
        state = _text(event["state"],32)
        stamp = _timestamp(event["timestamp"])
        if previous_time is not None and stamp < previous_time:
            raise ValueError("out of order event")
        old = states.get(task)
        if state not in _TRANSITIONS.get(old.state if old else None,set()):
            raise ValueError("invalid transition")
        if old and old.target != target:
            raise ValueError("target changed")
        record = TaskState(task,target,state,stamp.isoformat())
        states[task] = record
        history.append(record)
        previous_time = stamp
    active = [k for k,v in states.items() if v.state in ("queued","running")]
    selected = task_page(active,page)
    return {"tasks": tuple(states[k] for k in selected.task_ids),
            "pages": selected.pages, "history": tuple(history),
            "successful_tasks": sum(v.state=="succeeded" for v in states.values())}


def search_history(history, query=""):
    """Return the newest 100 matching journal events and the total match count."""
    query = query.strip().casefold()
    if not query:
        return list(reversed(history[-100:])), len(history)
    visible = []
    matches = 0
    for event in reversed(history):
        if not any(query in field.casefold() for field in
                             (event.task_id, event.target, event.state, event.timestamp)):
            continue
        matches += 1
        if len(visible) < 100:
            visible.append(event)
    return visible, matches
