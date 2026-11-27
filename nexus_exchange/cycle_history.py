"""Local cycle history for the desktop. The current brief keeps its original file format."""
from datetime import datetime, timezone
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


def _valid_digest(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class CycleHistory:
    def __init__(self, db):
        self.db = db
        db.execute("""CREATE TABLE IF NOT EXISTS cycle_briefs (
            digest TEXT PRIMARY KEY, finished TEXT NOT NULL, status TEXT NOT NULL, body BLOB NOT NULL)""")

    def earlier(self, current):
        digest = sha256(encode(current)).hexdigest() if current else ""
        # At most 29 bounded reports, validated one at a time. Index metadata
        # alone is not evidence of the report's status or timestamp.
        keys = self.db.execute("""SELECT CASE WHEN typeof(digest)='text'
            AND length(CAST(digest AS BLOB))=64 THEN CAST(digest AS BLOB) END
            FROM cycle_briefs WHERE digest != ? OR digest IS NULL
            ORDER BY rowid DESC LIMIT ?""", (digest, KEEP_CYCLES - 1)).fetchall()
        results = []
        seen = set()
        for (raw_key,) in keys:
            if type(raw_key) is not bytes:
                raise ValueError("Invalid saved cycle archive index.")
            try:
                key = raw_key.decode("ascii")
            except UnicodeDecodeError:
                raise ValueError("Invalid saved cycle archive index.") from None
            if not _valid_digest(key) or key in seen:
                raise ValueError("Invalid saved cycle archive index.")
            seen.add(key)
            try:
                brief = self.read(key)
                stamp = datetime.fromisoformat(brief["finished"]).astimezone(timezone.utc)
                results.append((key, stamp.replace(tzinfo=None).isoformat(timespec="seconds"), brief["status"]))
            except (ValueError, OverflowError):
                results.append((key, "", "Archive entry needs review"))
        return results

    def read(self, digest):
        if not _valid_digest(digest):
            raise ValueError("Saved cycle report unavailable.")
        rows = self.db.execute("""SELECT
            CASE WHEN typeof(body)='blob' AND length(body)<=? THEN body END,
            CASE WHEN typeof(finished)='text' AND length(CAST(finished AS BLOB))<=256
                THEN CAST(finished AS BLOB) END,
            CASE WHEN typeof(status)='text' AND length(CAST(status AS BLOB))<=256
                THEN CAST(status AS BLOB) END
            FROM cycle_briefs WHERE digest COLLATE BINARY=? LIMIT 2""",
                               (MAX_BYTES, digest)).fetchall()
        if len(rows) != 1:
            raise ValueError("Saved cycle report unavailable.")
        body, finished, status = rows[0]
        if type(body) is not bytes or sha256(body).hexdigest() != digest:
            raise ValueError("Saved cycle report unavailable.")
        brief = decode(body)
        if finished != brief["finished"].encode("utf-8") or status != brief["status"].encode("utf-8"):
            raise ValueError("Saved cycle report metadata mismatch.")
        return brief

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
                # Flush report data before publishing the directory entry.
                temp.flush()
                os.fsync(temp.fileno())
            check_active()
            try:
                previous = latest(directory)
            except (ValueError, RecursionError):
                previous = None
            if previous is not None:
                old = encode(previous)
                # A readable legacy encoding can expand when canonicalized.
                # Do not replace the only readable copy with an archive that
                # exceeds the read limit, or evict any older entries for it.
                if len(old) > MAX_BYTES:
                    raise ValueError("Saved cycle archive exceeds the size limit.")
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
            # Verify exact published bytes before returning a journal digest.
            # This is a bounded local read-back, not a power-loss guarantee.
            with target.open("rb") as handle:
                if handle.read(MAX_BYTES + 1) != raw:
                    raise ValueError("Saved cycle publication verification failed.")
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return sha256(raw).hexdigest()
