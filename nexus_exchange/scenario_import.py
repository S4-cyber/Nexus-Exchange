"""Strict local scenario manifest; never dispatch or treat historical evidence as live."""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from .economics import assess_deal
from .governor import Action, decide
from .local_import import _pairs, _constant, _integer, _decimal
from .opportunity_archive import OpportunityArchive
from .scout import _timestamp

FORMAT = "nexus-deal-scenario-v1"
MAX_BYTES = 256 * 1024

def _serialize(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported report value")

def evaluate_scenario(path, archive_path, *, halted=None, now=None):
    """Resolve an explicit historical snapshot and screen supplied counterparty terms."""
    decision = decide(Action.SIMULATE, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    now = datetime.now(timezone.utc) if now is None else now
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware evaluation time required")
    now = now.astimezone(timezone.utc)
    with Path(path).open("rb") as file:
        raw = file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("scenario file exceeds limit")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_constant,parse_int=_integer,parse_float=_decimal)
    except (UnicodeError,RecursionError) as exc:
        raise ValueError("invalid scenario JSON") from exc
    if type(data) is not dict or set(data)!={"format","opportunity_key","retrieved_at",
            "buyer","supplier","classifications","region","terms"} or data["format"]!=FORMAT:
        raise ValueError("invalid scenario manifest")
    key = data["opportunity_key"]
    if type(key) is not str or not re.fullmatch("[0-9a-f]{64}",key):
        raise ValueError("invalid opportunity key")
    stamp = _timestamp(data["retrieved_at"])
    with OpportunityArchive(archive_path) as archive:
        history = archive.recent(now=now,limit=100)
    matches = [r.observation for r in history if r.observation.opportunity.key==key]
    if not matches:
        raise ValueError("opportunity absent from newest 100 observations")
    observation = matches[0]
    if observation.opportunity.retrieved_at != stamp:
        raise ValueError("selected observation is absent or superseded")
    result = assess_deal(observation.opportunity,data["buyer"],data["supplier"],
        classifications=data["classifications"],region=data["region"],terms=data["terms"],
        now=now,halted=halted)
    report = dict(format="nexus-deal-report-v1", scope="Historical scenario; unverified assumptions; no commercial authority",
        evaluated_at=now.isoformat(),input_sha256=hashlib.sha256(raw).hexdigest(),
        observation=asdict(observation),assessment=asdict(result))
    return json.loads(json.dumps(report,default=_serialize,allow_nan=False))
