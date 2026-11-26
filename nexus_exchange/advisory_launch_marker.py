"""Private owner-held durable interlock; not process-tree containment."""
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
    rows = db.execute("SELECT slot,reservation_id FROM advisory_launch_v1 LIMIT 2").fetchall()
    if not rows:
        return None
    if len(rows) != 1 or rows[0][0] != 1:
        raise ValueError("invalid advisory launch marker cardinality")
    return _validate(rows[0][1])


def pending(db):
    return _read(db) is not None


def arm(db, token):
    _autocommit(db)
    _validate(token)
    if pending(db):
        raise PermissionError("previous advisory cleanup unconfirmed")
    db.execute("INSERT INTO advisory_launch_v1 VALUES (1,?)", (token,))


def clear(db, token):
    # Only the original owner may call this after the supervisor has joined.
    # A persisted token alone is not proof of child death.
    _autocommit(db)
    if _read(db) != _validate(token):
        raise PermissionError("advisory launch reservation mismatch")
    result = db.execute("DELETE FROM advisory_launch_v1 WHERE slot=1 AND reservation_id=?", (token,))
    if result.rowcount != 1:
        raise PermissionError("advisory launch marker changed")
