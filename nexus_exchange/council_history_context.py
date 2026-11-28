"""Owner-scoped Council context with separate, non-authoritative history.

This is a read-only advisory projection, not a Council attempt, model request,
commercial decision or authorization. All callbacks belong to the trusted runtime.
"""
from copy import deepcopy

from .advisory_current_scope import _compare_scope, _stamp
from .context_packet import build_packet
from .council_audit import validate_snapshot
from .local_advisory import _digest, _json, MAX_REQUEST_BYTES
from .quote_history_recall import _identity, build_recall
from .quote_history_reviewed import review_scoped_recall


def build_council_history_context(plan_id, *, limit, confirmed, inspect,
                                  compare, read_history, permit, clock):
    """Bracket exact reviewed RFQ recall with independently loaded Council scope.

    Historical references never enter the Council assumption evidence map,
    score, retry ledger or worker protocol. A cooperating local session is
    required; this is not a distributed snapshot or authenticated proof.
    """
    if confirmed is not True:
        raise PermissionError('explicit Council history consent required')
    _identity(plan_id)
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError('recall limit must be one to sixteen')
    permit()
    before = validate_snapshot(deepcopy(inspect()))
    if before['plan_id'] != plan_id:
        raise ValueError('Council history outside saved plan')
    history = review_scoped_recall(plan_id, limit=limit, confirmed=True,
                                   compare=compare, read_history=read_history,
                                   permit=permit)
    permit()
    current = validate_snapshot(deepcopy(inspect()))
    scope = _compare_scope(before, current, created=_stamp(before['evaluated_at']), now=clock())
    checked = _stamp(history['rechecked_at'])
    if not _stamp(before['evaluated_at']) <= checked <= _stamp(current['evaluated_at']):
        raise ValueError('RFQ review outside Council inspection interval')
    # Recall is newest-first, so this also detects future-dated matching rows
    # omitted by the result limit. Do not silently treat them as observations.
    if any(_stamp(row['rechecked_at']) > checked for row in history['recall']['references']):
        raise ValueError('historical observation postdates RFQ review')
    permit()
    # A final scoped read after the Council inspection binds even the retained
    # observations omitted from the bounded display. Do not retry on drift.
    recall = history['recall']
    if _json(recall) != _json(build_recall(read_history(), plan_id,
                                           recall['scope_sha256'], limit=limit)):
        raise ValueError('retained historical references changed during Council review')
    packet = build_packet(current, 'evidence', halted=False)
    payload = dict(format='nexus-council-history-context-v1', plan_id=plan_id,
                   original_snapshot_sha256=before['snapshot_sha256'],
                   current_scope_sha256=scope, council=packet, history=history,
                   history_used_for_scoring=False, current_decision=False,
                   independently_verified=False, external_authority=False,
                   dispatch_enabled=False, execution_eligible=False,
                   release_eligible=False)
    result = dict(payload, context_sha256=_digest(payload))
    if len(_json(result).encode('ascii')) > MAX_REQUEST_BYTES:
        raise ValueError('Council history context exceeds byte budget')
    permit()
    return result
