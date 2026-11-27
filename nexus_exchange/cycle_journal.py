"""Read-only correlation of a saved Scout brief with validated journal events."""
from datetime import datetime
import sqlite3
from hashlib import sha256
from .cycle_history import encode, decode


_EXPECTED = {
    'Completed': 'succeeded',
    'Partial coverage': 'succeeded',
    'No sources enabled': 'succeeded',
    'Sources unavailable': 'failed',
    'Research needs attention': 'failed',
}


def _stamp(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError('invalid timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.utcoffset() is None:
        raise ValueError('offset required')
    return stamp


def describe_outcome(brief, read_history):
    """Correlate IDs, timing and optional local content hash; never grant authority.

    read_history must return the independently validated, bounded journal history.
    No storage writes, retries or guessed terminal transitions are performed.
    """
    if 'cycle_id' not in brief:
        return 'Journal: legacy report — completion unconfirmed'
    key = brief['cycle_id']
    if type(key) is not str or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        return 'Journal: invalid cycle ID — completion unconfirmed'
    try:
        matches = [item for item in read_history() if item.task_id == key]
    except (ValueError, sqlite3.Error, OSError):
        return 'Journal: unavailable — completion unconfirmed'
    if not matches:
        return 'Journal: no matching cycle — completion unconfirmed'
    if any(item.target != 'Autonomous Scout cycle' for item in matches):
        return 'Journal: target mismatch — completion unconfirmed'
    last = matches[-1]
    if last.state in ('queued', 'running', 'cancelled', 'interrupted'):
        return f'Journal: {last.state} — completion unconfirmed'
    if last.state not in ('succeeded', 'failed'):
        return 'Journal: unknown outcome — completion unconfirmed'
    status = brief.get('status')
    if type(status) is not str or _EXPECTED.get(status) != last.state:
        return 'Journal: status mismatch — completion unconfirmed'
    try:
        running = next(item for item in matches if item.state == 'running')
        if not _stamp(running.timestamp) <= _stamp(brief.get('finished')) <= _stamp(last.timestamp):
            raise ValueError('timestamp order')
    except (ValueError, OverflowError, StopIteration):
        return 'Journal: timing mismatch — completion unconfirmed'
    digest = getattr(last, "report_sha256", None)
    if digest is None:
        return f'Journal: {last.state} (cycle ID match only)'
    try:
        raw = encode(brief)
        decode(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return 'Journal: invalid report — completion unconfirmed'
    if sha256(raw).hexdigest() != digest:
        return 'Journal: digest mismatch — completion unconfirmed'
    return f'Journal: {last.state} (report digest matches; local evidence only)'
