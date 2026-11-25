"""Bounded local advisory request/response contract; no inference or dispatch.

Only the trusted caller may provide a current Council snapshot and consent.
Digests associate data, not authenticated model identity or source facts.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re

MAX_REQUEST_BYTES=65536
MAX_RESPONSE_BYTES=16384
MAX_ATTEMPTS=3
TTL=timedelta(minutes=5)
_FLAGS=("independently_verified","execution_eligible","external_authority","dispatch_enabled")


def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)


def _digest(value):
    return sha256(_json(value).encode("ascii")).hexdigest()


def _pin(value):
    if type(value) is not str or not re.fullmatch("[a-f0-9]{64}",value) or value=="0"*64:
        raise ValueError("exact nonzero digest required")
    return value


def _utc(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError("aware timestamp required")
    return now.astimezone(timezone.utc)


def _permit(approved,halted):
    from .governor import Action,decide
    if approved is not True or not decide(Action.RESEARCH_LOCAL,halted=halted).allowed:
        raise PermissionError("explicit local advisory consent and running state required")


def build_request(snapshot,model_sha256,attempt,*,now,approved=None,halted=None):
    """Project exact validated Council data into a reference-only request."""
    _permit(approved,halted)
    from .context_packet import build_packet
    now=_utc(now)
    _pin(model_sha256)
    if type(attempt) is not int or not 1<=attempt<=MAX_ATTEMPTS:
        raise ValueError("advisory attempt outside three-attempt ceiling")
    packet=build_packet(snapshot,"evidence",halted=halted)
    evaluated=datetime.fromisoformat(packet["evaluated_at"])
    if not timedelta(0)<=now-_utc(evaluated)<=TTL:
        raise ValueError("current Council snapshot required")
    review=packet["data"]["review"]
    fields=[]
    for key,refs in sorted(packet["data"]["evidence"].items()):
        state=("UNKNOWN_ASSUMPTION" if key in review["unknown_fields"] else
               "MISSING_REFERENCE" if not refs else "REFERENCES_REQUIRE_VERIFICATION")
        fields.append(dict(field=key,state=state,reference_ids=list(refs)))
    payload=dict(format="nexus-local-advice-request-v1",model_sha256=model_sha256,attempt=attempt,
        created_at=now.isoformat(timespec="microseconds"),snapshot_sha256=packet["snapshot_sha256"],
        packet_sha256=packet["packet_sha256"],source_hold=packet["data"]["summary"]["source_hold"],
        fields=fields,**dict.fromkeys(_FLAGS,False))
    result=dict(payload,request_sha256=_digest(payload))
    if len(_json(result).encode("ascii"))>MAX_REQUEST_BYTES:
        raise ValueError("advisory request exceeds byte budget")
    return result


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:
            raise ValueError("duplicate advisory member")
        result[key]=value
    return result


def _constant(_value):
    raise ValueError("nonstandard JSON constant")


def _parse_advice(raw,request):
    """Parse response against an already validated trusted request."""
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_RESPONSE_BYTES:
        raise ValueError("advisory response exceeds byte budget")
    try:
        value=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_constant=_constant)
    except (UnicodeError,ValueError,RecursionError):
        raise ValueError("invalid advisory JSON") from None
    if (type(value) is not dict or set(value)!={"format","request_sha256","model_sha256","advice"}
            or value["format"]!="nexus-local-advice-response-v1"
            or value["request_sha256"]!=request["request_sha256"]
            or value["model_sha256"]!=request["model_sha256"]):
        raise ValueError("advisory response identity or schema mismatch")
    fields={row["field"]:row for row in request["fields"]}
    rows=value["advice"]
    if type(rows) is not list or len(rows)>len(fields):
        raise ValueError("invalid advisory item count")
    seen=set()
    for row in rows:
        if (type(row) is not dict or set(row)!={"field","reason","reference_id"}
                or type(row["field"]) is not str or row["field"] not in fields or row["field"] in seen):
            raise ValueError("invalid or repeated advisory field")
        field=fields[row["field"]]
        if row["reason"]!=field["state"]:
            raise ValueError("advisory reason contradicts validated context")
        ref=row["reference_id"]
        if field["reference_ids"]:
            if type(ref) is not str or ref not in field["reference_ids"]:
                raise ValueError("advisory reference outside field scope")
        elif ref is not None:
            raise ValueError("unexpected advisory reference")
        seen.add(row["field"])
    return dict(format="nexus-local-advice-review-v1",request_sha256=request["request_sha256"],
        model_sha256=request["model_sha256"],response_sha256=sha256(raw).hexdigest(),
        advice=rows,source_hold=request["source_hold"],
        unresolved_fields=[row["field"] for row in request["fields"] if not row["reference_ids"]],
        **dict.fromkeys(_FLAGS,False))


def review_response(raw,request,snapshot,*,now,approved=None,halted=None):
    """Reconstruct exact request from a fresh trusted snapshot before review."""
    _permit(approved,halted)
    now=_utc(now)
    if type(request) is not dict or type(request.get("created_at")) is not str:
        raise ValueError("exact advisory request required")
    try:
        created=_utc(datetime.fromisoformat(request["created_at"]))
        if not timedelta(0)<=now-created<=TTL:
            raise ValueError("advisory request expired or future dated")
        if not timedelta(0)<=now-_utc(datetime.fromisoformat(snapshot["evaluated_at"]))<=TTL:
            raise ValueError("current Council snapshot required")
        expected=build_request(snapshot,request.get("model_sha256"),request.get("attempt"),
                               now=created,approved=approved,halted=halted)
        if _json(request)!=_json(expected):
            raise ValueError("advisory request differs from exact Council projection")
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError):
        raise ValueError("invalid or stale advisory request") from None
    return _parse_advice(raw,expected)
