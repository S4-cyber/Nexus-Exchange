"""Read user-selected compiled snapshots, never fetch URLs or execute input."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from .governor import Action, decide
from .pipeline import evaluate_snapshots
from .scout import _text, _timestamp, _url

MAX_BYTES = 2 * 1024 * 1024
MAX_RELEASES = 100
FORMAT = "nexus-compiled-snapshots-v1"

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result

def _integer(token):
    if len(token) > 17:
        raise ValueError("integer outside import limits")
    return int(token)

def _decimal(token):
    if len(token) > 64:
        raise ValueError("decimal outside import limits")
    value = Decimal(token)
    if not value.is_finite() or not -12 <= value.as_tuple().exponent <= 12 or value.adjusted() > 12:
        raise ValueError("decimal outside import limits")
    return value

def _constant(token):
    raise ValueError("nonfinite JSON constant")

def evaluate_file(path, *, halted=None, now=None):
    """Read one explicit manifest. Metadata and compiled tags are source assertions."""
    decision = decide(Action.RESEARCH_LOCAL, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    now = datetime.now(timezone.utc) if now is None else now
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware evaluation time required")
    with Path(path).open("rb") as file:
        raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("file exceeds import limit")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_int=_integer, parse_float=_decimal, parse_constant=_constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid or deeply nested JSON") from exc
    if type(manifest) is not dict or set(manifest) != {"format","publisher","source_url","retrieved_at","releases"}:
        raise ValueError("invalid snapshot manifest")
    if manifest["format"] != FORMAT:
        raise ValueError("unsupported import format")
    publisher = _text(manifest["publisher"],100)
    if publisher != manifest["publisher"] or publisher.casefold() == "demo":
        raise ValueError("invalid or reserved publisher")
    source_url = _url(manifest["source_url"])
    retrieved = _timestamp(manifest["retrieved_at"])
    if retrieved > now:
        raise ValueError("future retrieval")
    releases = manifest["releases"]
    if type(releases) is not list or not 1 <= len(releases) <= MAX_RELEASES:
        raise ValueError("bounded nonempty release list required")
    for release in releases:
        if type(release) is not dict or release.get("tag") != ["compiled"]:
            raise ValueError("compiled snapshots required; incremental releases unsupported")
    return evaluate_snapshots(publisher,releases,source_url,retrieved.isoformat(),
        now=now,halted=halted)
