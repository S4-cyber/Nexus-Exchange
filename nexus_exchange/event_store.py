"""Local SQLite event journal; trusted single-application boundary only."""
import sqlite3
import json
from contextlib import closing
from datetime import datetime, timezone
from .scout import _timestamp
from .dashboard_events import project, validate_event

MAX_RECOVERY_EVENTS=100000
# Worst-case ASCII JSON escaping of the permitted 128/256-character fields
# fits within this per-record limit, including non-BMP Unicode.
MAX_EVENT_BYTES=8192
# Logical UTF-8 payload budget, not a database-file or process-RSS limit.
MAX_JOURNAL_BYTES=64*1024*1024
# UTC recovery stamps always have this fixed-width ISO format.
_RECOVERY_STAMP_EXAMPLE="2000-01-01T00:00:00.000000+00:00"


def _unique_fields(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate journal field")
        result[key]=value
    return result


def _decode(payload):
    try:
        return json.loads(payload, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError) as exc:
        raise ValueError("invalid journal payload") from exc


def _encode(event):
    return json.dumps(event, allow_nan=False, sort_keys=True)


def _interruption(item, stamp):
    return dict(task_id=item.task_id,target=item.target,
                state="interrupted",timestamp=stamp)


def _check_byte_budget(rows, payloads, reserved_bytes=0):
    total=reserved_bytes+sum(len(row[1].encode("utf-8")) for row in rows)
    for payload in payloads:
        size=len(payload.encode("utf-8"))
        if not 1<=size<=MAX_EVENT_BYTES:
            raise ValueError("invalid journal payload storage")
        total+=size
    if total>MAX_JOURNAL_BYTES:
        raise ValueError("journal byte capacity review required")


class EventStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    def read(self):
        events=tuple(_decode(row[1]) for row in self._rows())
        project(events)
        return events
    def _rows(self):
        return tuple(self._iter_rows())

    def _iter_rows(self):
        # Guard size and storage class before transferring payloads into Python.
        # Cast to BLOB so malformed UTF-8 is handled explicitly, not by SQLite's
        # text decoder. Never omit corrupt rows from the ordered history.
        total=0
        for index,(seq,raw) in enumerate(self.db.execute(
            """SELECT seq, CASE WHEN typeof(payload)='text'
                AND length(CAST(payload AS BLOB)) BETWEEN 1 AND ?
                THEN CAST(payload AS BLOB) END
                FROM events ORDER BY seq LIMIT ?""",
            (MAX_EVENT_BYTES,MAX_RECOVERY_EVENTS+1))):
            if index>=MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            if type(raw) is not bytes or b"\x00" in raw:
                raise ValueError("invalid journal payload storage")
            total+=len(raw)
            if total>MAX_JOURNAL_BYTES:
                raise ValueError("journal byte capacity review required")
            try:
                decoded=raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid journal payload encoding") from exc
            yield seq,decoded

    def _verify_append(self, before, payloads):
        # Compare the full ordered history without materializing a second copy.
        with closing(self._iter_rows()) as after:
            for row in before:
                if next(after,None)!=row:
                    raise ValueError("journal mutation not persisted")
            for payload in payloads:
                row=next(after,None)
                if row is None or row[1]!=payload:
                    raise ValueError("journal mutation not persisted")
            if next(after,None) is not None:
                raise ValueError("journal mutation not persisted")

    def append(self, event):
        validate_event(event)
        payload = _encode(event)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._rows()
            view=project((*tuple(_decode(row[1]) for row in rows), json.loads(payload)))
            latest={item.task_id:item for item in view["history"]}
            active=tuple(item for item in latest.values() if item.state in ("queued","running"))
            # Reserve both rows and exact serialized bytes for every active task.
            if len(rows)+1+len(active)>MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            reserved=sum(len(_encode(_interruption(item,_RECOVERY_STAMP_EXAMPLE)).encode("utf-8"))
                         for item in active)
            _check_byte_budget(rows,(payload,),reserved)
            self.db.execute("INSERT INTO events(payload) VALUES (?)", (payload,))
            self._verify_append(rows,(payload,))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
    def recover_interrupted(self, *, now):
        """Reconcile orphaned queued/running work only under exclusive app ownership.

        No task is replayed. All transitions commit atomically or none do.
        """
        if type(now) is not datetime or now.utcoffset() is None:
            raise ValueError("aware recovery clock required")
        stamp=now.astimezone(timezone.utc).isoformat(timespec="microseconds")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._rows()
            events=tuple(_decode(row[1]) for row in rows)
            view=project(events)
            history=view["history"]
            if history and _timestamp(history[-1].timestamp)>_timestamp(stamp):
                raise ValueError("recovery clock precedes journal")
            latest={item.task_id:item for item in history}
            interrupted=tuple(_interruption(item,stamp)
                for item in latest.values() if item.state in ("queued","running"))
            if len(events)+len(interrupted)>MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            project((*events,*interrupted))
            payloads=tuple(_encode(item) for item in interrupted)
            _check_byte_budget(rows,payloads)
            self.db.executemany("INSERT INTO events(payload) VALUES (?)", ((payload,) for payload in payloads))
            self._verify_append(rows,payloads)
            self.db.execute("COMMIT")
            return len(interrupted)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()
