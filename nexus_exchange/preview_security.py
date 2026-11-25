"""Bind bounded security-review reports; not independent security attestation."""
import json
import re
from hashlib import sha256

MAX_SECURITY_REPORT_BYTES = 256 * 1024
BUILD_REPORT = "BUILD-INVENTORY.json"
SOURCE_REPORT = "SOURCE-REVIEW.json"
_FLAGS = ("independently_verified", "vulnerabilities_cleared", "license_compliance_verified",
          "secrets_history_scanned", "frozen_binary_sbom_complete", "publisher_authenticated",
          "release_eligible", "external_authority")


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _hex(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _decode(raw, format_name, scope, fields):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SECURITY_REPORT_BYTES:
        raise ValueError("security report size")
    try:
        value = json.loads(raw.decode("ascii"))
        if type(value) is not dict or _canonical(value) + b"\n" != raw:
            raise ValueError("noncanonical security report")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ValueError("invalid security report") from None
    if (set(value) != set(fields) | {"format", "scope", "report_sha256", *_FLAGS}
            or value["format"] != format_name or value["scope"] != scope
            or any(value[key] is not False for key in _FLAGS)):
        raise ValueError("security report schema or authority mismatch")
    claimed = value["report_sha256"]
    if not _hex(claimed) or claimed != sha256(_canonical({k: v for k, v in value.items() if k != "report_sha256"})).hexdigest():
        raise ValueError("security report digest mismatch")
    return value, dict(sha256=sha256(raw).hexdigest(), bytes=len(raw), report_sha256=claimed)


def _short(value, maximum=200):
    return type(value) is str and 1 <= len(value) <= maximum and value.isascii() and value.isprintable()


def security_report_refs(build_raw, source_raw, *, packager_versions):
    """Verify local consistency and expected scope, not authenticity or vulnerability clearance."""
    build, build_ref = _decode(build_raw, "nexus-release-security-inventory-v1",
        "INSTALLED_BUILD_ENVIRONMENT_NOT_FROZEN_CONTENTS",
        ("python", "sqlite", "openssl", "unicode_database", "pinned_packager_versions_checked", "distributions"))
    if (build["pinned_packager_versions_checked"] is not True
            or any(not _short(build[k]) for k in ("python", "sqlite", "openssl", "unicode_database"))):
        raise ValueError("build pin review required")
    rows = build["distributions"]
    if type(rows) is not list or not 1 <= len(rows) <= 128:
        raise ValueError("distribution inventory size")
    actual = {}
    for row in rows:
        if (type(row) is not dict or set(row) != {"name", "version", "license_expression_hint", "license_metadata_hint"}
                or not _short(row["name"], 80) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", row["name"])
                or not _short(row["version"], 80) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,79}", row["version"])
                or any(row[k] is not None and not _short(row[k]) for k in ("license_expression_hint", "license_metadata_hint"))
                or row["name"] in actual):
            raise ValueError("invalid build inventory row")
        actual[row["name"]] = row["version"]
    if (list(actual) != sorted(actual) or any(actual.get(k) != v for k, v in packager_versions.items())
            or not set(actual) <= set(packager_versions) | {"pip"}):
        raise ValueError("build package version drift")
    source, source_ref = _decode(source_raw, "nexus-source-tripwires-v1", "APPLICATION_PYTHON_SOURCE_ONLY",
                                 ("source_files", "files", "findings_count"))
    rows = source["files"]
    if (type(rows) is not list or not 2 <= len(rows) <= 256 or type(source["source_files"]) is not int
            or source["source_files"] != len(rows) or type(source["findings_count"]) is not int
            or source["findings_count"] != 0):
        raise ValueError("source review incomplete or findings present")
    paths = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"path", "sha256", "bytes", "imports", "network_imports", "findings"}
                or type(row["path"]) is not str or not (row["path"] == "desktop.py" or
                    re.fullmatch(r"nexus_exchange/[a-z_][a-z0-9_]*\.py", row["path"]))
                or not _hex(row["sha256"]) or type(row["bytes"]) is not int or not 1 <= row["bytes"] <= 512 * 1024
                or type(row["findings"]) is not list or row["findings"]
                or any(type(row[k]) is not list or any(type(v) is not str for v in row[k]) for k in ("imports", "network_imports"))):
            raise ValueError("invalid source inventory row")
        paths.append(row["path"])
    if paths[0] != "desktop.py" or paths != sorted(set(paths)):
        raise ValueError("source inventory path mismatch")
    return {BUILD_REPORT: build_ref, SOURCE_REPORT: source_ref}
