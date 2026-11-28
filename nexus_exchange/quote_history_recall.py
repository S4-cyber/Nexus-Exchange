"""Bounded historical references for advisory review, never action authority."""
from datetime import datetime, timezone
import hashlib
import json
import re


def _identity(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('exact historical identity required')
    return value


def validate_recall_request(plan_id, scope_sha256, limit):
    _identity(plan_id)
    _identity(scope_sha256)
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError('recall limit must be one to sixteen')


def build_recall(rows, plan_id, scope_sha256, *, limit=8):
    """Project fresh trusted-store metadata, not arbitrary external evidence.

    One representative per commercial snapshot, ordered by recheck time then
    receipt ID; repeated observations do not crowd out distinct snapshots.
    Counts describe only retained records, not verified events or supersession.
    """
    validate_recall_request(plan_id, scope_sha256, limit)
    if type(rows) is not list or len(rows) > 64:
        raise ValueError('bounded historical recall batch required')
    seen, groups = set(), {}
    for row in rows:
        if (type(row) is not dict or row.get('plan_id') != plan_id
                or row.get('historical_only') is not True
                or row.get('current_status') != 'NOT_REVALIDATED'
                or row.get('external_authority') is not False
                or row.get('execution_eligible') is not False):
            raise ValueError('historical recall scope or authority mismatch')
        receipt = _identity(row.get('receipt_sha256'))
        snapshot = _identity(row.get('snapshot_sha256'))
        scope = _identity(row.get('scope_sha256'))
        if receipt in seen:
            raise ValueError('duplicate historical recall identity')
        seen.add(receipt)
        raw = row.get('rechecked_at')
        if type(raw) is not str or len(raw) > 40:
            raise ValueError('bounded recall timestamp required')
        try:
            stamp = datetime.fromisoformat(raw)
            if stamp.utcoffset() is None:
                raise ValueError('aware timestamp required')
            stamp = stamp.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError('invalid recall timestamp') from None
        if scope == scope_sha256:
            groups.setdefault(snapshot, []).append((stamp, receipt))
    references = []
    for snapshot, observations in groups.items():
        stamp, receipt = max(observations)
        references.append((stamp, receipt, dict(receipt_sha256=receipt,
            snapshot_sha256=snapshot, rechecked_at=stamp.isoformat(),
            observations=len(observations))))
    references.sort(key=lambda item: item[:2], reverse=True)
    payload = dict(format='nexus-historical-recall-v1', plan_id=plan_id,
        scope_sha256=scope_sha256, limit=limit,
        matching_receipts=sum(map(len, groups.values())),
        distinct_snapshots=len(groups), truncated=len(groups) > limit,
        references=[item[2] for item in references[:limit]], historical_only=True,
        current_status='NOT_REVALIDATED', supersession_status='NOT_ESTABLISHED',
        current_decision=False, independently_verified=False,
        external_authority=False, execution_eligible=False)
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return dict(payload, recall_sha256=hashlib.sha256(encoded.encode('ascii')).hexdigest())
