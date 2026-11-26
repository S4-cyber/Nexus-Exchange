"""Local SQLite event journal; trusted single-application boundary only."""
import sqlite3
import json
from datetime import datetime, timezone
from .scout import _timestamp
from .dashboard_events import project

MAX_RECOVERY_EVENTS=100000
# Worst-case ASCII JSON escaping of the permitted 128/256-character fields
# fits within this per-record limit, including non-BMP Unicode.
MAX_EVENT_BYTES=8192


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


class EventStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    def read(self):
        events=tuple(_decode(row[1]) for row in self._rows())
        project(events)
        return events
    def _rows(self):
        # Guard size and storage class before transferring payloads into Python.
        # Cast to BLOB so malformed UTF-8 is handled explicitly, not by SQLite's
        # text decoder. Never omit corrupt rows from the ordered history.
        rows=[]
        for seq,raw in self.db.execute(
            """SELECT seq, CASE WHEN typeof(payload)='text'
                AND length(CAST(payload AS BLOB)) BETWEEN 1 AND ?
                THEN CAST(payload AS BLOB) END
                FROM events ORDER BY seq LIMIT ?""",
            (MAX_EVENT_BYTES,MAX_RECOVERY_EVENTS+1)):
            if len(rows)>=MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            if type(raw) is not bytes or b"\x00" in raw:
                raise ValueError("invalid journal payload storage")
            try:
                rows.append((seq,raw.decode("utf-8")))
            except UnicodeDecodeError as exc:
                raise ValueError("invalid journal payload encoding") from exc
        return tuple(rows)

    def _verify_append(self, before, payloads):
        after=self._rows()
        if after[:len(before)]!=before or tuple(row[1] for row in after[len(before):])!=payloads:
            raise ValueError("journal mutation not persisted")

    def append(self, event):
        payload = json.dumps(event, allow_nan=False, sort_keys=True)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._rows()
            view=project((*tuple(_decode(row[1]) for row in rows), json.loads(payload)))
            latest={item.task_id:item.state for item in view["history"]}
            # Reserve space for an interruption record for every active task.
            if len(rows)+1+sum(state in ("queued","running") for state in latest.values())>MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
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
            interrupted=tuple(dict(task_id=item.task_id,target=item.target,
                                   state="interrupted",timestamp=stamp)
                for item in latest.values() if item.state in ("queued","running"))
            if len(events)+len(interrupted)>MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            project((*events,*interrupted))
            payloads=tuple(json.dumps(item,allow_nan=False,sort_keys=True) for item in interrupted)
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
