"""Group already validated local receipt projections, not authenticated history."""
from collections import Counter

MAX_INDEX_RECEIPTS = 64


def annotate_history(rows):
    """Bounded batch-relative counts; chronology never establishes supersession.

    Only call with projections from inspect_receipt, not raw external records.
    This adds no current decision, authority, or persistent storage.
    """
    if type(rows) is not list or len(rows) > MAX_INDEX_RECEIPTS:
        raise ValueError("historical lineage batch exceeds budget")
    unique = {}
    for row in rows:
        if (type(row) is not dict or row.get("historical_only") is not True
                or row.get("current_status") != "NOT_REVALIDATED"
                or row.get("external_authority") is not False
                or row.get("execution_eligible") is not False):
            raise ValueError("historical projection required")
        key = row["receipt_sha256"]
        if key in unique and unique[key] != row:
            raise ValueError("conflicting historical receipt projection")
        unique[key] = row
    counts = Counter()
    snapshots = {}
    for row in unique.values():
        scope = (row["plan_id"], row["scope_sha256"])
        snapshot = row["snapshot_sha256"]
        counts[(*scope, snapshot)] += 1
        snapshots.setdefault(scope, set()).add(snapshot)
    ordered = sorted(unique.values(), key=lambda row: (row["rechecked_at"], row["receipt_sha256"]),
                     reverse=True)
    return [dict(row, snapshot_observations=counts[(row["plan_id"], row["scope_sha256"], row["snapshot_sha256"])],
                 scope_snapshots=len(snapshots[(row["plan_id"], row["scope_sha256"])]),
                 supersession_status="NOT_ESTABLISHED") for row in ordered]
