"""Local cycle history for the desktop. The current brief keeps its original file format."""
from datetime import datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


BRIEF = "engagement-latest.json"
KEEP_CYCLES = 30
MAX_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 64


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate cycle report field.")
        result[key] = value
    return result


def _validate_json(value, depth=0):
    # Validate before canonical encoding or handing any value to native UI.
    if depth > MAX_JSON_DEPTH:
        raise ValueError("Saved cycle report nesting exceeds the limit.")
    if isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8")
            _validate_json(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item, depth + 1)
    elif isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite cycle report number.")


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("Saved cycle report exceeds the size limit.")
    try:
        brief = json.loads(raw, object_pairs_hook=_unique_fields)
        _validate_json(brief)
    except (ValueError, RecursionError):
        raise ValueError("Invalid saved cycle report JSON.") from None
    if (not isinstance(brief, dict) or brief.get("format") != "nexus-engagement-brief-v1"
            or not isinstance(brief.get("status"), str) or not isinstance(brief.get("finished"), str)
            or len(brief["status"]) > 64 or len(brief["finished"]) > 64
            or not isinstance(brief.get("jobs"), dict)
            or not all(isinstance(brief.get(k), list) for k in ("notes", "shortlist", "sources"))):
        raise ValueError("Invalid saved cycle report.")
    if datetime.fromisoformat(brief["finished"]).utcoffset() is None:
        raise ValueError("Invalid cycle timestamp.")
    return brief


def latest(directory):
    try:
        with (Path(directory) / BRIEF).open("rb") as handle:
            return decode(handle.read(MAX_BYTES + 1))
    except FileNotFoundError:
        return None


def encode(brief):
    return json.dumps(brief, ensure_ascii=True, sort_keys=True, allow_nan=False).encode("ascii")


class CycleHistory:
    def __init__(self, db):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS cycle_briefs (
            digest TEXT PRIMARY KEY, finished TEXT NOT NULL, status TEXT NOT NULL, body BLOB NOT NULL)""")

    def earlier(self, current):
        digest = sha256(encode(current)).hexdigest() if current else ""
        return self.db.execute("""SELECT digest,strftime('%Y-%m-%dT%H:%M:%S',finished),status FROM cycle_briefs
            WHERE digest != ? AND typeof(digest)='text' AND length(digest)=64
            AND typeof(status)='text' AND length(CAST(status AS BLOB))<=256
            AND typeof(finished)='text' AND length(finished)<=64 AND julianday(finished) IS NOT NULL
            ORDER BY rowid DESC LIMIT ?""", (digest, KEEP_CYCLES - 1)).fetchall()

    def read(self, digest):
        row = self.db.execute("""SELECT body FROM cycle_briefs
            WHERE digest=? AND typeof(body)='blob' AND length(body)<=?""", (digest, MAX_BYTES)).fetchone()
        if row is None or sha256(row[0]).hexdigest() != digest:
            raise ValueError("Saved cycle report unavailable.")
        return decode(row[0])

    def publish(self, directory, brief, check_active):
        # RuntimeGuard gives the desktop sole ownership. Preserve the previous brief
        # before the atomic replacement. A cancelled/retried replacement is idempotent.
        raw = encode(brief)
        decode(raw)
        target = Path(directory) / BRIEF
        temp_path = None
        try:
            with NamedTemporaryFile(dir=directory, prefix=".cycle-", suffix=".tmp", delete=False) as temp:
                temp_path = Path(temp.name)
                temp.write(raw)
            check_active()
            try:
                previous = latest(directory)
            except (ValueError, RecursionError):
                previous = None
            if previous is not None:
                old = encode(previous)
                expected = (sha256(old).hexdigest(), previous["finished"], previous["status"], old)
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute("""INSERT INTO cycle_briefs VALUES (?,?,?,?)
                        ON CONFLICT(digest) DO NOTHING""", expected)
                    self.db.execute("""DELETE FROM cycle_briefs WHERE rowid IN
                        (SELECT rowid FROM cycle_briefs ORDER BY rowid DESC LIMIT -1 OFFSET ?)""",
                                    (KEEP_CYCLES,))
                    check_active()
                    # A conflict, ignored insert or trigger must not silently
                    # discard the previous brief. Compare in SQLite so corrupt
                    # oversized bodies are never transferred to Python.
                    verified = self.db.execute("""SELECT count(*), count(CASE WHEN
                        typeof(digest)='text' AND digest COLLATE BINARY=?
                        AND typeof(finished)='text' AND finished COLLATE BINARY=?
                        AND typeof(status)='text' AND status COLLATE BINARY=?
                        AND typeof(body)='blob' AND body=? THEN 1 END)
                        FROM cycle_briefs WHERE digest=?""", (*expected, expected[0])).fetchone()
                    count = self.db.execute("SELECT count(*) FROM (SELECT 1 FROM cycle_briefs LIMIT ?)",
                                            (KEEP_CYCLES + 1,)).fetchone()
                    if verified != (1, 1) or count[0] > KEEP_CYCLES:
                        raise ValueError("Saved cycle archive verification failed.")
                    self.db.execute("COMMIT")
                except BaseException:
                    if self.db.in_transaction:
                        self.db.execute("ROLLBACK")
                    raise
            check_active()
            os.replace(temp_path, target)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return sha256(raw).hexdigest()
