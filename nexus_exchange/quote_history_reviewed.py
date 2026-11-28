"""Derive historical recall scope from a freshly rechecked local comparison.

Internal trusted-runtime helper, not an agent callback or authenticated input.
The two comparisons bracket a local history read, not a distributed transaction.
No raw quotation terms or independently verified facts are returned.
"""
from copy import deepcopy

from .operator_drafts import _digest, _json
from .quote_history import historical_receipt
from .quote_history_recall import _identity, build_recall


def review_scoped_recall(plan_id, *, limit, confirmed, compare, read_history, permit):
    """Return reference-only history for the exact independently loaded RFQ basket.

    The runtime supplies all three callbacks and owns the exclusive local session.
    Caller-supplied comparison projections or scope hashes are not accepted there.
    """
    if confirmed is not True:
        raise PermissionError('explicit local quotation history review required')
    _identity(plan_id)
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError('recall limit must be one to sixteen')
    permit()
    before = deepcopy(compare())
    if type(before) is not dict or before.get('plan_id') != plan_id:
        raise ValueError('reviewed comparison outside saved plan')
    scope = _identity(before.get('scope_sha256'))
    historical_receipt(before, before)
    permit()
    recall = build_recall(read_history(), plan_id, scope, limit=limit)
    permit()
    checked = historical_receipt(before, compare())
    payload = dict(format='nexus-reviewed-history-context-v1',
                   reviewed_comparison_sha256=before['comparison_sha256'],
                   rechecked_comparison_sha256=checked['rechecked_comparison_sha256'],
                   rechecked_at=checked['rechecked_at'], recall=recall,
                   historical_only=True, current_decision=False,
                   independently_verified=False, external_authority=False,
                   execution_eligible=False)
    result = dict(payload, context_sha256=_digest(_json(payload)))
    permit()
    return result
