"""Local progress rows for desktop oversight, alongside the existing task journal."""
from datetime import datetime, timezone
from hashlib import sha256
import json

STATES = ("Pending", "Engaged", "Completed", "Finding", "Needs attention", "Stopped", "Skipped")
JOURNAL_STATES = dict(queued="Pending", running="Engaged", succeeded="Completed",
                      failed="Needs attention", cancelled="Stopped", interrupted="Stopped")
LIMIT = 5000


class ActivityFeed:
    def __init__(self, db):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS scout_activity(
            item TEXT PRIMARY KEY, run TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL,
            detail TEXT NOT NULL, stamp TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS scout_activity_run ON scout_activity(run,state)")

    def put(self, run, rows, now):
        stamp = now.astimezone(timezone.utc).isoformat(timespec="microseconds")
        values = []
        for key, state, title, detail in rows:
            if state not in STATES:
                raise ValueError("Unknown activity state")
            values.append((key, run, state, title[:512], detail[:2048], stamp))
        if not values:
            return
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.executemany("INSERT OR REPLACE INTO scout_activity VALUES (?,?,?,?,?,?)", values)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def settle(self, run=None, *, failed=False):
        # An interrupted cycle never leaves a queued or engaged row looking live after restart.
        state = "Needs attention" if failed else "Stopped"
        detail = "Cycle interrupted before completion." if failed else "Stopped before completion."
        sql = "UPDATE scout_activity SET state=?,detail=?,stamp=? WHERE state IN ('Pending','Engaged')"
        args = [state, detail, datetime.now(timezone.utc).isoformat()]
        if run is not None:
            sql += " AND run=?"
            args.append(run)
        self.db.execute(sql, args)
        self.db.execute("""DELETE FROM scout_activity WHERE rowid IN (
            SELECT rowid FROM scout_activity WHERE state NOT IN ('Pending','Engaged')
            ORDER BY rowid DESC LIMIT -1 OFFSET ?)""", (LIMIT,))

    def snapshot(self):
        by_key = {}
        for key, state, title, detail, stamp in self.db.execute(
                "SELECT item,state,title,detail,stamp FROM scout_activity ORDER BY rowid DESC"):
            by_key[key] = (key, state, title, detail, stamp)
        # Fold transitions from earlier releases and manual tools into one row per task.
        journal = {}
        for (raw,) in self.db.execute("SELECT payload FROM events ORDER BY seq DESC LIMIT ?", (LIMIT,)):
            ev = json.loads(raw)
            key = "journal-" + ev["task_id"]
            state = JOURNAL_STATES[ev["state"]]
            transition = state + " " + ev["timestamp"][:19].replace("T", " ") + " UTC"
            if key not in journal:
                journal[key] = [key, state, ev["target"], [], ev["timestamp"]]
            journal[key][3].append(transition)
        for key, state, title, transitions, stamp in journal.values():
            by_key[key] = (key, state, title, " → ".join(reversed(transitions)) + "\nTask " + key[8:], stamp)
        return sorted(by_key.values(), key=lambda row: row[4], reverse=True)


def finding_row(source, label, lead):
    identity = sha256((source + "\0" + lead["notice_id"]).encode()).hexdigest()
    lines = [label + " · " + lead["notice_id"]]
    deadline = lead.get("deadline") or lead.get("earliest_deadline_date")
    if deadline:
        lines.append("Reported deadline: " + deadline)
    tasks = lead.get("todo") or []
    if tasks and isinstance(tasks[0].get("instruction"), str):
        lines.append(tasks[0]["instruction"])
    lines.append(lead["source_url"])
    return ("finding-" + identity, "Finding", lead["title"], "\n".join(lines))
