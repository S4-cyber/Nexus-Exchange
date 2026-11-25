"""Local SQLite event journal; trusted single-application boundary only."""
import sqlite3
import json
from .dashboard_events import project

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
    def close(self):
        self.db.close()
