"""Private owner-held durable interlock; not process-tree containment."""
from contextlib import contextmanager
import re


def _validate(token):
    if type(token) is not str or re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise ValueError("invalid advisory launch reservation")
    return token


def _autocommit(db):
    if db.isolation_level is not None or db.in_transaction:
        raise PermissionError("durable advisory marker requires autocommit")


def initialize(db):
    _autocommit(db)
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS advisory_launch_v1 (
        slot INTEGER PRIMARY KEY CHECK(slot=1), reservation_id TEXT NOT NULL)""")
    pending(db)


def _read(db):
    # Bound corrupted fields before materialization. Return bytes to avoid
    # SQLite's implicit UTF-8 decoding of malformed stored text.
    rows = db.execute("""SELECT
        CASE WHEN typeof(slot)='integer' AND slot=1 THEN 1 END,
        CASE WHEN typeof(reservation_id)='text'
             AND length(CAST(reservation_id AS BLOB))=64
             THEN CAST(reservation_id AS BLOB) END
        FROM advisory_launch_v1 LIMIT 2""").fetchall()
    if not rows:
        return None
    if len(rows) != 1 or rows[0][0] != 1:
        raise ValueError("invalid advisory launch marker cardinality")
    raw = rows[0][1]
    if type(raw) is not bytes:
        raise ValueError("invalid advisory launch reservation")
    try:
        token = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("invalid advisory launch reservation") from None
    return _validate(token)


def pending(db):
    return _read(db) is not None



def validate_snapshot(db):
    """Validate an optional offline marker without initializing or clearing it."""
    schema = db.execute("SELECT type FROM sqlite_master WHERE name=?",
                        ("advisory_launch_v1",)).fetchone()
    if schema is None:
        return False
    if schema != ("table",) or db.execute("PRAGMA table_xinfo(advisory_launch_v1)").fetchall() != [
        (0, "slot", "INTEGER", 0, None, 1, 0),
        (1, "reservation_id", "TEXT", 1, None, 0, 0),
    ]:
        raise ValueError("invalid advisory launch schema")
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' "
                  "AND tbl_name='advisory_launch_v1' LIMIT 1").fetchone():
        raise ValueError("unexpected advisory launch trigger")
    return pending(db)


@contextmanager
def _mutation(db):
    _autocommit(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise


def arm(db, token):
    _validate(token)
    with _mutation(db):
        if pending(db):
            raise PermissionError("previous advisory cleanup unconfirmed")
        result = db.execute("INSERT INTO advisory_launch_v1 VALUES (1,?)", (token,))
        if result.rowcount != 1 or _read(db) != token:
            raise PermissionError("advisory launch marker not persisted")


def clear(db, token):
    # Only the original owner may call this after the supervisor has joined.
    # A persisted token alone is not proof of child death.
    _validate(token)
    with _mutation(db):
        if _read(db) != token:
            raise PermissionError("advisory launch reservation mismatch")
        result = db.execute("DELETE FROM advisory_launch_v1 WHERE slot=1 AND reservation_id=?", (token,))
        if result.rowcount != 1 or pending(db):
            raise PermissionError("advisory launch marker changed")
