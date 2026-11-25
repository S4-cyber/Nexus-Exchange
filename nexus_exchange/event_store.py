"""Local SQLite event journal; trusted single-application boundary only."""
import sqlite3
import json
from datetime import datetime, timezone
from .scout import _timestamp
from .dashboard_events import project

MAX_RECOVERY_EVENTS=100000

class EventStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
    def read(self):
        return tuple(json.loads(row[0]) for row in self.db.execute("SELECT payload FROM events ORDER BY seq"))
    def append(self, event):
        payload = json.dumps(event, allow_nan=False, sort_keys=True)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            project((*self.read(), json.loads(payload)))
            self.db.execute("INSERT INTO events(payload) VALUES (?)", (payload,))
            self.db.execute("COMMIT")
        except BaseException:
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
            rows=self.db.execute("SELECT payload FROM events ORDER BY seq LIMIT ?",
                                 (MAX_RECOVERY_EVENTS+1,)).fetchall()
            if len(rows)>MAX_RECOVERY_EVENTS:
                raise ValueError("journal recovery capacity review required")
            events=tuple(json.loads(row[0]) for row in rows)
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
            self.db.executemany("INSERT INTO events(payload) VALUES (?)",
                ((json.dumps(item,allow_nan=False,sort_keys=True),) for item in interrupted))
            self.db.execute("COMMIT")
            return len(interrupted)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()
