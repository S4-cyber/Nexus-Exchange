"""Bounded storage and projection of Scout activity, not authority."""
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
    seen = set()
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
            if key in seen:
                raise ValueError('duplicate Scout activity identity')
            seen.add(key)
            try:
                moment = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if moment.utcoffset() is None:
                    raise ValueError('offset required')
                stamp = moment.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                raise ValueError('invalid Scout activity timestamp') from None
            result.append((key, state, title, detail, stamp))
    return result


def _write_text(value, limit, *, truncate=False):
    if type(value) is not str:
        raise ValueError('invalid Scout activity field type')
    if truncate:
        value = value[:limit]
    if len(value) > limit or '\x00' in value:
        raise ValueError('invalid Scout activity field length or content')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeEncodeError:
        raise ValueError('invalid Scout activity encoding') from None
    return value, size


def write_scout_rows(db, run, rows, now, states):
    """Bound incoming batches and verify final targeted rows before commit.

    Last write wins within a batch, as in the original activity feed. This
    bounds batch payload, not the complete database or SQLite process memory.
    """
    run, run_bytes = _write_text(run, 512)
    if not run.strip() or not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('invalid Scout activity run or timestamp')
    try:
        stamp = now.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError):
        raise ValueError('invalid Scout activity timestamp') from None
    values = []
    total = 0
    for index, row in enumerate(rows):
        if index >= MAX_ROWS:
            raise ValueError('Scout activity batch row capacity review required')
        if type(row) not in (tuple, list) or len(row) != 4:
            raise ValueError('invalid Scout activity row')
        fields = [_write_text(value, limit, truncate=position >= 2)
                  for position, (value, limit) in enumerate(zip(row, (512, 32, 512, 2048)))]
        key, state, title, detail = (field[0] for field in fields)
        if (not key.strip() or key.startswith('journal-') or key == HOLD_KEY
                or state not in states):
            raise ValueError('invalid Scout activity identity or state')
        total += run_bytes + len(stamp) + sum(field[1] for field in fields)
        if total > MAX_BYTES:
            raise ValueError('Scout activity batch byte capacity review required')
        values.append((key, run, state, title, detail, stamp))
    if not values:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        db.executemany('INSERT OR REPLACE INTO scout_activity VALUES (?,?,?,?,?,?)', values)
        # Compare in SQLite: an unexpected large or malformed stored value is
        # never transferred to Python. Check final values after all inserts.
        columns = ('item', 'run', 'state', 'title', 'detail', 'stamp')
        predicate = ' AND '.join(f"typeof({column})='text' AND {column} COLLATE BINARY=?"
                                 for column in columns)
        sql = (f'SELECT count(*), count(CASE WHEN {predicate} THEN 1 END) '
               'FROM scout_activity WHERE item=?')
        for key, expected in {row[0]: row for row in values}.items():
            with closing(db.execute(sql, (*expected, key))) as cursor:
                if cursor.fetchone() != (1, 1):
                    raise ValueError('Scout activity write verification failed')
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
