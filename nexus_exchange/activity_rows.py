"""Bounded storage and projection of Scout activity, not authority."""
from datetime import datetime, timezone
from contextlib import closing
from itertools import zip_longest

MAX_ROWS = 10000  # Includes terminal and active records; never silently truncate.
MAX_BYTES = 32 * 1024 * 1024  # Logical payload, not process RSS or database size.
HOLD_KEY = 'scout-activity-review-required'
_ACTIVE = ('Pending', 'Engaged')
_STOPPED = ('Stopped', 'Stopped before completion.')
_INTERRUPTED = ('Needs attention', 'Cycle interrupted before completion.')
_STAMP_BYTES = len('2000-01-01T00:00:00.000000+00:00')
_RECOVERY_BYTES = max(sum(len(value) for value in pair) for pair in (_STOPPED, _INTERRUPTED)) + _STAMP_BYTES
_COLUMNS = (('item', 512), ('run', 512), ('state', 32), ('title', 512), ('detail', 2048), ('stamp', 64))
_SELECT = ','.join(
    f"CASE WHEN typeof({column})='text' AND length(CAST({column} AS BLOB)) <= {limit * 4} "
    f"THEN CAST({column} AS BLOB) END" for column, limit in _COLUMNS
)


def _iter_scout_rows(db, states, *, full=False, reserve=False):
    """Stream validated rows, including the persisted run in the byte budget."""
    seen = set()
    total = 0
    with closing(db.execute(f'SELECT rowid,{_SELECT} FROM scout_activity ORDER BY rowid DESC LIMIT ?',
                            (MAX_ROWS + 1,))) as cursor:
        for index, raw in enumerate(cursor):
            if index >= MAX_ROWS:
                raise ValueError('Scout activity row capacity review required')
            values = []
            for value, (_, limit) in zip(raw[1:], _COLUMNS):
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
            key, run, state, title, detail, stamp = values
            if (not run.strip() or not key.strip() or key.startswith('journal-') or key == HOLD_KEY
                    or state not in states):
                raise ValueError('invalid Scout activity identity or state')
            if key in seen:
                raise ValueError('duplicate Scout activity identity')
            seen.add(key)
            if reserve and state in _ACTIVE:
                total += max(0, _RECOVERY_BYTES - sum(len(value.encode('utf-8'))
                                                     for value in (state, detail, stamp)))
                if total > MAX_BYTES:
                    raise ValueError('Scout activity recovery byte capacity review required')
            try:
                moment = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if moment.utcoffset() is None:
                    raise ValueError('offset required')
                stamp = moment.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError):
                raise ValueError('invalid Scout activity timestamp') from None
            yield (raw[0], *values) if full else (key, state, title, detail, stamp)


def read_scout_rows(db, states):
    """Reject corrupt or oversized projections as a whole on a caller-owned DB."""
    with closing(_iter_scout_rows(db, states)) as rows:
        return list(rows)


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
    bounds both batch and final activity-table payload, not the SQLite file or
    process memory. Existing invalid data requires explicit maintenance.
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
        # The final table must remain readable within the same projection
        # budget. Stream rather than retaining a second full snapshot. This
        # also rejects malformed non-target rows before the transaction commits.
        with closing(_iter_scout_rows(db, states, reserve=True)) as persisted:
            for _ in persisted:
                pass
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise



def settle_scout_rows(db, run, failed, now, states, terminal_limit):
    """Atomically settle interrupted rows and verify the existing retention policy."""
    if run is not None:
        run, _ = _write_text(run, 512)
        if not run.strip():
            raise ValueError('invalid Scout activity settlement run')
    if type(failed) is not bool or type(terminal_limit) is not int or terminal_limit < 0:
        raise ValueError('invalid Scout activity settlement policy')
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('invalid Scout activity settlement timestamp')
    try:
        stamp = now.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError):
        raise ValueError('invalid Scout activity settlement timestamp') from None
    state, detail = _INTERRUPTED if failed else _STOPPED
    db.execute('BEGIN IMMEDIATE')
    try:
        expected = []
        terminal = 0
        # Preserve exact raw values and row order for all retained records.
        # Older terminal rows are removed only by the pre-existing retention rule.
        with closing(_iter_scout_rows(db, states, full=True)) as before:
            for row in before:
                rowid, key, scope, current, title, previous_detail, previous_stamp = row
                if current in _ACTIVE and (run is None or scope == run):
                    row = (rowid, key, scope, state, title, detail, stamp)
                if row[3] not in _ACTIVE:
                    terminal += 1
                    if terminal > terminal_limit:
                        continue
                expected.append(row)
        sql = "UPDATE scout_activity SET state=?,detail=?,stamp=? WHERE state IN ('Pending','Engaged')"
        args = [state, detail, stamp]
        if run is not None:
            sql += " AND run=?"
            args.append(run)
        db.execute(sql, args)
        db.execute("""DELETE FROM scout_activity WHERE rowid IN (
            SELECT rowid FROM scout_activity WHERE state NOT IN ('Pending','Engaged')
            ORDER BY rowid DESC LIMIT -1 OFFSET ?)""", (terminal_limit,))
        with closing(_iter_scout_rows(db, states, full=True, reserve=True)) as after:
            if any(actual != wanted for actual, wanted in zip_longest(after, expected)):
                raise ValueError('Scout activity settlement verification failed')
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
