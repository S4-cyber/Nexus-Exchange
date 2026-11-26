"""Local progress rows for desktop oversight, alongside the existing task journal."""
from datetime import datetime, timezone
from hashlib import sha256
import sqlite3

from .event_store import read_projection
from .activity_rows import HOLD_KEY, read_scout_rows, write_scout_rows

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
        write_scout_rows(self.db, run, rows, now, STATES)

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
        try:
            for key, state, title, detail, stamp in read_scout_rows(self.db, STATES):
                by_key[key] = (key, state, title, detail, stamp)
        except (ValueError, sqlite3.DatabaseError):
            # A failed Scout projection cannot mask independent journal status.
            by_key[HOLD_KEY] = (HOLD_KEY, "Needs attention", "Scout activity unavailable",
                               "Activity validation or read failed. Review local storage; no Scout status inferred.",
                               datetime.now(timezone.utc).isoformat())
        # Fold transitions from earlier releases and manual tools into one row per task.
        journal = {}
        try:
            history = read_projection(self.db)["history"]
        except (ValueError, sqlite3.DatabaseError):
            # Never show partially validated task states or raw journal contents.
            # Independent Scout findings remain available for review.
            key = "journal-review-required"
            by_key[key] = (key, "Needs attention", "Task journal unavailable",
                           "Journal validation or read failed. Review local storage; no task status inferred.",
                           datetime.now(timezone.utc).isoformat())
            return sorted(by_key.values(), key=lambda row: row[4], reverse=True)
        for ev in reversed(history[-LIMIT:]):
            key = "journal-" + ev.task_id
            state = JOURNAL_STATES[ev.state]
            transition = state + " " + ev.timestamp[:19].replace("T", " ") + " UTC"
            if key not in journal:
                journal[key] = [key, state, ev.target, [], ev.timestamp]
            journal[key][3].append(transition)
        for key, state, title, transitions, stamp in journal.values():
            by_key[key] = (key, state, title, " → ".join(reversed(transitions)) + "\nTask " + key[8:], stamp)
        return sorted(by_key.values(), key=lambda row: row[4], reverse=True)


def finding_key(source, notice_id):
    return "finding-" + sha256((source + "\0" + notice_id).encode()).hexdigest()


def with_shortlist(rows, brief):
    """Make the latest review reasoning searchable, including briefs saved before the feed."""
    if not brief:
        return rows
    result = {row[0]: row for row in rows}
    old_keys = {(title, detail.splitlines()[-1]): key for key, state, title, detail, stamp in rows
                if state == "Finding" and detail}
    for item in brief["shortlist"]:
        title, url = item["title"], item["url"]
        key = (finding_key(item["source"], item["notice_id"]) if item.get("notice_id") else
               old_keys.get((title, url)) or finding_key("previous-brief", title + "\0" + url))
        existing = result.get(key)
        stamp = existing[4] if existing else brief["finished"]
        detail = existing[3] if existing else url
        reason = item["review"].replace("_", " ").lower()
        note = "Latest shortlist · " + reason + "\n" + item["next_step"]
        result[key] = (key, "Finding", title, note + "\n" + detail, stamp)
    return sorted(result.values(), key=lambda row: row[4], reverse=True)


def finding_row(source, label, lead):
    lines = [label + " · " + lead["notice_id"]]
    deadline = lead.get("deadline") or lead.get("earliest_deadline_date")
    if deadline:
        lines.append("Reported deadline: " + deadline)
    tasks = lead.get("todo")
    if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
        instruction = tasks[0].get("instruction")
        if isinstance(instruction, str):
            lines.append(instruction[:2048].encode("utf-8", errors="replace").decode("utf-8"))
    lines.append(lead["source_url"])
    return (finding_key(source, lead["notice_id"]), "Finding", lead["title"], "\n".join(lines))
