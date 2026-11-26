"""Bounded read-only projection of persisted Scout activity, not authority."""
from datetime import datetime, timezone
from contextlib import closing

MAX_ROWS = 10000  # Includes terminal and active records; never silently truncate.
MAX_BYTES = 32 * 1024 * 1024  # Logical payload, not process RSS or database size.
HOLD_KEY = 'scout-activity-review-required'
_COLUMNS = (('item', 512), ('state', 32), ('title', 512), ('detail', 2048), ('stamp', 64))
_SELECT = ','.join(
    f"CASE WHEN typeof({column})='text' AND length(CAST({column} AS BLOB)) <= {limit * 4} "
    f"THEN CAST({column} AS BLOB) END" for column, limit in _COLUMNS
)


def read_scout_rows(db, states):
    """Reject corrupt or oversized projections as a whole on a caller-owned DB."""
    result = []
    total = 0
    with closing(db.execute(f'SELECT {_SELECT} FROM scout_activity ORDER BY rowid DESC LIMIT ?',
                            (MAX_ROWS + 1,))) as cursor:
        for index, raw in enumerate(cursor):
            if index >= MAX_ROWS:
                raise ValueError('Scout activity row capacity review required')
            values = []
            for value, (_, limit) in zip(raw, _COLUMNS):
                if type(value) is not bytes or b'\x00' in value:
                    raise ValueError('invalid Scout activity storage')
                total += len(value)
                if total > MAX_BYTES:
                    raise ValueError('Scout activity byte capacity review required')
                try:
                    decoded = value.decode('utf-8')
                except UnicodeDecodeError:
                    raise ValueError('invalid Scout activity encoding') from None
                if len(decoded) > limit:
                    raise ValueError('invalid Scout activity field length')
                values.append(decoded)
            key, state, title, detail, stamp = values
            if (not key.strip() or key.startswith('journal-') or key == HOLD_KEY
                    or state not in states):
                raise ValueError('invalid Scout activity identity or state')
            try:
                moment = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if moment.utcoffset() is None:
                    raise ValueError('offset required')
                stamp = moment.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                raise ValueError('invalid Scout activity timestamp') from None
            result.append((key, state, title, detail, stamp))
    return result
