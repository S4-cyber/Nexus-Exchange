"""Rebind advisory review to a freshly inspected trusted saved-plan scope.

Only a cooperating owner can supply actual ScenarioCouncil inspections.
Neither snapshot integrity nor comparison authenticates that caller.
"""
from datetime import datetime, timezone

from .local_advisory import TTL, _digest, _json, _utc, review_response

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_CLOCK_FIELDS = {'evaluated_at', 'snapshot_sha256', 'schedule_sha256',
                 'modeled_collection_wait_us'}


def _stamp(value):
    return _utc(datetime.fromisoformat(value))


def _stable(snapshot, stamp):
    # Saved plan ID is content-addressed over immutable context, scenario and
    # schedule inputs. The schedule assessment digest itself includes the clock.
    stable = {key: value for key, value in snapshot.items() if key not in _CLOCK_FIELDS}
    wait = snapshot['modeled_collection_wait_us']
    elapsed = stamp - _EPOCH
    micros = (elapsed.days * 86400 + elapsed.seconds) * 1000000 + elapsed.microseconds
    stable['modeled_collection_at_us'] = None if wait is None else micros + wait
    return stable


def _compare_scope(original, current, *, created, now):
    """Private comparison of already validated trusted Council snapshots."""
    created, now = _utc(created), _utc(now)
    before, after = _stamp(original['evaluated_at']), _stamp(current['evaluated_at'])
    if not before <= created <= after <= now or now - before > TTL:
        raise ValueError('fresh advisory scope inspection required')
    for key in ('schedule_sha256', 'snapshot_sha256'):
        if (original[key] == current[key]) != (before == after):
            raise ValueError('advisory scope clock pin mismatch')
    first, second = _stable(original, before), _stable(current, after)
    if _json(first) != _json(second):
        raise ValueError('advisory saved-plan scope changed')
    return _digest(first)


def review_current_response(raw, request, original, current, *, now, approved=None, halted=None,
                            history_pin=None, current_history_pin=None):
    """Validate exact original request, then compare an independent fresh inspection.

    The runtime owner must obtain current from its own ScenarioCouncil after
    child cleanup. This helper never inspects a directory or grants authority.
    The exact original snapshot is still required; never rewrite its timestamp
    or accept a child-supplied current snapshot. All stable fields, including
    reference IDs, source holds, model outputs and criterion states, must match.
    """
    review = review_response(raw, request, original, now=now,
                             approved=approved, halted=halted, history_pin=history_pin)
    from .council_audit import validate_snapshot
    original = validate_snapshot(original)
    current = validate_snapshot(current)
    scope = _compare_scope(original, current, created=_stamp(request['created_at']), now=now)
    from .advisory_history_pin import match_history_pins, pin_for_snapshot
    pinned = match_history_pins(history_pin, current_history_pin)
    if pinned is not None:
        pin_for_snapshot(pinned, current)
    return dict(review, current_snapshot_sha256=current['snapshot_sha256'],
                current_evaluated_at=current['evaluated_at'], current_scope_sha256=scope)
