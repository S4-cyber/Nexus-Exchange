"""Offline development references, never executable agent instructions or authority."""
import argparse
import copy
from datetime import date
import json
from pathlib import Path
import re
import stat

FORMAT = "nexus-awesome-catalog-v1"
TOPIC = "https://github.com/topics/awesome"
MAX_BYTES = 256 * 1024
MAX_RESOURCES = 128
WORKSTREAMS = tuple("H%02d" % i for i in range(1, 9))
CATEGORIES = ("index", "language", "infrastructure", "local-inference", "agents", "security", "data")
_FLAGS = ("auto_install", "auto_execute", "external_authority")
_FIELDS = {"repository", "revision", "category", "priority", "workstreams", "license_hint",
           "license_basis", "evidence", "purpose", "next_check", "adoption"}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate catalogue key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonstandard JSON number")


def _matches(value, pattern):
    return type(value) is str and re.fullmatch(pattern, value) is not None


def _text(value, limit):
    return type(value) is str and 1 <= len(value) <= limit and value.isascii() and value.isprintable()


def parse_catalog(raw):
    """Validate a bounded reference-only registry; never retrieve its links."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("resource catalogue size")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("invalid resource catalogue JSON") from error
    if (type(data) is not dict or set(data) != {"format", "surveyed_at", "topic", "resources", *_FLAGS}
            or data["format"] != FORMAT or data["topic"] != TOPIC
            or any(data[key] is not False for key in _FLAGS)
            or not _matches(data["surveyed_at"], r"[0-9]{4}-[0-9]{2}-[0-9]{2}")):
        raise ValueError("resource catalogue schema or authority")
    date.fromisoformat(data["surveyed_at"])
    rows = data["resources"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_RESOURCES:
        raise ValueError("resource count")
    seen = set()
    for row in rows:
        if (type(row) is not dict or set(row) != _FIELDS
                or not _matches(row["repository"], r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
                or not _matches(row["revision"], r"[a-f0-9]{40}") or row["revision"] == "0" * 40
                or row["category"] not in CATEGORIES
                or type(row["priority"]) is not int or not 1 <= row["priority"] <= 3
                or not _matches(row["license_hint"], r"[A-Za-z0-9][A-Za-z0-9.+-]{0,79}")
                or row["license_basis"] not in ("METADATA_ONLY", "LICENSE_FILE_OBSERVED", "UNRESOLVED")
                or not _text(row["purpose"], 240) or not _text(row["next_check"], 320)
                or row["adoption"] != "REFERENCE_ONLY"):
            raise ValueError("invalid resource entry")
        key = row["repository"].casefold()
        if key in seen:
            raise ValueError("duplicate resource repository")
        seen.add(key)
        streams = row["workstreams"]
        if (type(streams) is not list or not 1 <= len(streams) <= len(WORKSTREAMS)
                or any(type(item) is not str or item not in WORKSTREAMS for item in streams)
                or len(set(streams)) != len(streams)):
            raise ValueError("invalid resource workstreams")
        evidence = row["evidence"]
        if type(evidence) is not list or not 1 <= len(evidence) <= 4:
            raise ValueError("resource evidence count")
        paths = set()
        for item in evidence:
            if (type(item) is not dict or set(item) != {"path", "blob"}
                    or not _matches(item["path"], r"[A-Za-z0-9_.-]{1,120}(?:/[A-Za-z0-9_.-]{1,120}){0,5}")
                    or any(part in (".", "..") for part in item["path"].split("/"))
                    or item["path"] in paths or not _matches(item["blob"], r"[a-f0-9]{40}")
                    or item["blob"] == "0" * 40):
                raise ValueError("invalid pinned resource evidence")
            paths.add(item["path"])
        if row["license_basis"] == "LICENSE_FILE_OBSERVED" and not any(
                path.rsplit("/", 1)[-1].upper().startswith("LICENSE") for path in paths):
            raise ValueError("missing license evidence path")
    return data


def read_catalog(path):
    """Read only the selected local metadata file; no network or installation."""
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_BYTES:
        raise ValueError("resource catalogue file type or size")
    with path.open("rb") as handle:
        return parse_catalog(handle.read(MAX_BYTES + 1))


def shortlist(catalog, *, workstream=None, category=None):
    """Return independent copies of pinned references ordered by review priority."""
    if workstream is not None and workstream not in WORKSTREAMS:
        raise ValueError("unknown workstream")
    if category is not None and category not in CATEGORIES:
        raise ValueError("unknown category")
    checked = parse_catalog(json.dumps(catalog, ensure_ascii=True, allow_nan=False).encode("ascii"))
    rows = []
    for row in checked["resources"]:
        if (workstream is None or workstream in row["workstreams"]) and (category is None or row["category"] == category):
            item = copy.deepcopy(row)
            item["url"] = "https://github.com/" + row["repository"] + "/tree/" + row["revision"]
            rows.append(item)
    return sorted(rows, key=lambda row: (row["priority"], row["repository"].casefold()))


def main():
    parser = argparse.ArgumentParser(description="Offline reference catalogue; no agent or execution authority")
    parser.add_argument("--workstream", choices=WORKSTREAMS)
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "resources" / "awesome" / "catalog.json")
    args = parser.parse_args()
    result = shortlist(read_catalog(args.catalog), workstream=args.workstream, category=args.category)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
