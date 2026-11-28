"""E25: local, evidence-bound organizational recipient declarations.

Neither domain consistency nor a file fingerprint verifies ownership, identity,
consent or authorization. This module has no network or delivery operation.
"""
from contextlib import contextmanager
from datetime import timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from .evidence import parse_reference
from .operator_drafts import (_FLAGS, _digest, _hash, _json, _permit, _scheme,
    _shape, _stamp, _stored_stamp, _text, _validated, render_rfq)
from .scout import _timestamp

FORMAT="nexus-operator-recipient-v1"
MAX_RECIPIENTS=10000
MAX_PAYLOAD=16384
MAX_AGE=timedelta(hours=24)
ROLE_MAILBOXES=frozenset({"procurement","purchasing","sales","quotes","rfq","bids",
    "tenders","contracts","inquiries","enquiries","info"})
_FLAGS_EXTRA=(*_FLAGS,"independently_verified","mailbox_control_verified",
    "source_authenticity_verified","contact_permission_verified")
_FIELDS={"scheme","identifier","organization_name","email","source_url","observed_at"}
_SCOPE={"plan_id","draft_id","supplier_profile_sha256","supplier"}
_RECORD={"version","candidate","recorded_at"}
_DOMAIN_LABEL=re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")

def _scope(draft):
    validated=_validated(draft)
    request=validated["request"]
    if validated["format"]!="nexus-operator-rfq-v2":
        raise ValueError("recipient declaration requires scoped RFQ v2")
    return dict(plan_id=request["plan_id"],draft_id=validated["draft_id"],
        supplier_profile_sha256=request["supplier_profile_sha256"],supplier=request["supplier"])

def _normalize_scope(raw):
    _shape(raw,_SCOPE)
    _shape(raw["supplier"],{"scheme","identifier"})
    return dict(plan_id=_hash(raw["plan_id"]),draft_id=_hash(raw["draft_id"]),
        supplier_profile_sha256=_hash(raw["supplier_profile_sha256"]),
        supplier=dict(scheme=_scheme(raw["supplier"]["scheme"]),
                      identifier=_text(raw["supplier"]["identifier"],128)))

def _contact(raw):
    _shape(raw,_FIELDS)
    email=_text(raw["email"],254)
    if not email.isascii() or email!=email.lower() or email.count("@")!=1:
        raise ValueError("canonical organization role mailbox required")
    local,domain=email.split("@")
    labels=domain.split(".")
    if (local not in ROLE_MAILBOXES or len(domain)>253 or len(labels)<2
            or any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels)
            or re.fullmatch("[a-z]{2,63}",labels[-1]) is None):
        raise ValueError("organization role mailbox required; no personal mailbox")
    url=_text(raw["source_url"],1024)
    if not url.isascii() or any(c.isspace() for c in url) or "\\" in url:
        raise ValueError("invalid declared contact source")
    parsed=urlsplit(url)
    if (parsed.scheme!="https" or parsed.netloc not in (domain,"www."+domain)
            or parsed.query or parsed.fragment or parsed.geturl()!=url
            or "?" in url or "#" in url):
        raise ValueError("declared contact source must be HTTPS on the exact mailbox domain or its www host")
    observed=_timestamp(raw["observed_at"])
    return dict(scheme=_scheme(raw["scheme"]),identifier=_text(raw["identifier"],128),
        organization_name=_text(raw["organization_name"],256),email=email,
        source_url=url,observed_at=_stamp(observed))

def _bind(scope,contact):
    if (contact["scheme"],contact["identifier"])!=(scope["supplier"]["scheme"],scope["supplier"]["identifier"]):
        raise ValueError("recipient declaration differs from saved supplier identity")

def _fresh(contact,now):
    _stamp(now)
    observed=_timestamp(contact["observed_at"])
    if observed>now or now-observed>MAX_AGE:
        raise ValueError("recipient observation is future-dated or stale")

def validate_declaration(draft,raw,*,organization_name,now,halted=None):
    _permit(halted)
    scope=_scope(draft)
    contact=_contact(raw)
    _bind(scope,contact)
    if contact["organization_name"]!=_text(organization_name,256):
        raise ValueError("recipient organization differs from reentered supplier declaration")
    _fresh(contact,now)
    return contact

def _candidate(scope,contact,reference):
    scope=_normalize_scope(scope)
    contact=_contact(contact)
    _bind(scope,contact)
    parse_reference(reference)
    payload=dict(format=FORMAT,scope=scope,recipient=contact,evidence_reference=reference)
    return dict(payload,recipient_id=_digest(_json(payload)),**dict.fromkeys(_FLAGS_EXTRA,False))

def prepare_recipient(draft,raw,*,organization_name,evidence_reference,now,halted=None):
    contact=validate_declaration(draft,raw,organization_name=organization_name,now=now,halted=halted)
    return _candidate(_scope(draft),contact,evidence_reference)

def _canonical(candidate):
    _shape(candidate,{"format","scope","recipient","evidence_reference","recipient_id",*_FLAGS_EXTRA})
    expected=_candidate(candidate["scope"],candidate["recipient"],candidate["evidence_reference"])
    if candidate!=expected or any(candidate[k] is not False for k in _FLAGS_EXTRA):
        raise ValueError("recipient declaration identity or authority mismatch")
    return expected

def _for_draft(draft,candidate):
    canonical=_canonical(candidate)
    if canonical["scope"]!=_scope(draft):
        raise ValueError("recipient declaration outside exact saved draft scope")
    return canonical

def render_correspondence(draft,candidate,*,halted=None):
    """Local preview text only; no mailto link, mail client or send operation."""
    _permit(halted)
    recipient=_for_draft(draft,candidate)["recipient"]
    return "\n".join(("LOCAL CORRESPONDENCE DRAFT — DO NOT SEND",
        "Declared organization (unverified): "+recipient["organization_name"],
        "Proposed role mailbox (unverified): "+recipient["email"],
        "Declared contact source (not fetched): "+recipient["source_url"],
        "Subject: Request for quotation (non-binding draft)","",
        render_rfq(draft,halted=False),"",
        "Mailbox control, source authenticity and contact permission remain unverified."))

# Bound all projected columns in SQLite, before Python materializes a damaged row.
# Do not filter out corrupt rows: NULL sentinels must fail closed in _decode.
_READ_COLUMNS = ", ".join(f"CASE WHEN typeof({column})='text' AND length(CAST({column} AS BLOB))<={limit} THEN {column} END"
             for column,limit in (("recipient_id",64),("plan_id",64),("draft_id",64),
                                  ("recorded_at",40),("payload","?"),("digest",64)))

def _decode(row):
    key,plan_id,draft_id,stamp,payload,digest=row
    if (any(type(value) is not str for value in row) or len(payload)>MAX_PAYLOAD
            or not payload.isascii() or _digest(payload)!=digest):
        raise ValueError("recipient storage integrity mismatch")
    try:
        data=json.loads(payload)
    except (ValueError, RecursionError):
        raise ValueError("recipient storage validation failed") from None
    _shape(data,_RECORD)
    if type(data["version"]) is not int or data["version"]!=1:
        raise ValueError("unsupported recipient record version")
    candidate=_canonical(data["candidate"])
    created=_stored_stamp(data["recorded_at"])
    _fresh(candidate["recipient"],_timestamp(created))
    if (candidate["recipient_id"],candidate["scope"]["plan_id"],candidate["scope"]["draft_id"],created)!=(key,plan_id,draft_id,stamp) or _json(data)!=payload:
        raise ValueError("stored recipient identity mismatch")
    return data

def _view(data):
    return dict(data,state="DECLARED_RECIPIENT_DRAFT_ONLY",historical_only=True,
        **dict.fromkeys(_FLAGS_EXTRA,False))

class RecipientStore:
    """Trusted local immutable role-contact records; no authenticated party or approval."""
    def __init__(self,path,*,existing_only=False):
        if type(existing_only) is not bool:
            raise ValueError("invalid recipient storage mode")
        path=Path(path)
        if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
            raise ValueError("invalid recipient database path")
        if existing_only and not path.is_file():
            raise ValueError("existing recipient database required")
        self.db=sqlite3.connect(path.resolve().as_uri()+"?mode=rw",uri=True,
            timeout=5,isolation_level=None) if existing_only else sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            if existing_only and self.db.execute("SELECT type FROM sqlite_master WHERE name=?",
                    ("operator_recipients_v1",)).fetchone()!=("table",):
                raise ValueError("recipient storage schema missing")
            if not existing_only:
                self.db.execute("""CREATE TABLE IF NOT EXISTS operator_recipients_v1(
                    recipient_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,draft_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL)""")
                self.db.execute("""CREATE INDEX IF NOT EXISTS operator_recipient_scope_v1
                    ON operator_recipients_v1(plan_id,draft_id,recorded_at DESC,recipient_id)""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self
    def __exit__(self,*exc):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def save(self,draft,candidate,*,confirmed=None,now,halted=None):
        _permit(halted)
        if confirmed is not True:
            raise PermissionError("explicit local recipient-record confirmation required")
        candidate=_for_draft(draft,candidate)
        _fresh(candidate["recipient"],now)
        stamp=_stamp(now)
        key=candidate["recipient_id"]
        scope=candidate["scope"]
        with self._transaction():
            # Do not allow a damaged database to suppress or rewrite a declaration.
            for catalog in ("sqlite_master", "sqlite_temp_master"):
                if self.db.execute("SELECT 1 FROM "+catalog+" WHERE type='trigger' AND tbl_name=? COLLATE NOCASE LIMIT 1",
                        ("operator_recipients_v1",)).fetchone() is not None:
                    raise ValueError("unexpected recipient storage trigger")
            row=self.db.execute("SELECT "+_READ_COLUMNS+" FROM operator_recipients_v1 WHERE recipient_id=?",
                (MAX_PAYLOAD,key)).fetchone()
            if row is not None:
                existing=_decode(row)
                if existing["candidate"]!=candidate or stamp<existing["recorded_at"]:
                    raise ValueError("recipient replay mismatch or clock moved backward")
                return _view(existing)
            if self.db.execute("SELECT COUNT(*) FROM operator_recipients_v1").fetchone()[0]>=MAX_RECIPIENTS:
                raise ValueError("recipient storage capacity review required")
            data=dict(version=1,candidate=candidate,recorded_at=stamp)
            payload=_json(data)
            digest=_digest(payload)
            row=(key,scope["plan_id"],scope["draft_id"],stamp,payload,digest)
            _decode(row)
            inserted=self.db.execute("INSERT INTO operator_recipients_v1 VALUES (?,?,?,?,?,?)",row)
            stored=self.db.execute("SELECT "+_READ_COLUMNS+" FROM operator_recipients_v1 WHERE recipient_id=?",
                (MAX_PAYLOAD,key)).fetchone()
            if inserted.rowcount!=1 or stored!=row or _decode(stored)!=data:
                raise ValueError("recipient storage publication mismatch")
            return _view(data)

    def list_draft(self,draft,*,limit=100,halted=None):
        _permit(halted)
        scope=_scope(draft)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid recipient history limit")
        rows=self.db.execute("SELECT "+_READ_COLUMNS+"""
            FROM operator_recipients_v1 WHERE plan_id=? AND draft_id=?
            ORDER BY recorded_at DESC,recipient_id LIMIT ?""",
            (MAX_PAYLOAD,scope["plan_id"],scope["draft_id"],limit+1)).fetchall()
        records=[]
        for row in rows:
            data=_decode(row)
            _for_draft(draft,data["candidate"])
            records.append(_view(data))
        return dict(scope=scope,rows=records[:limit],truncated=len(records)>limit,
            historical_only=True,**dict.fromkeys(_FLAGS_EXTRA,False))


    def get(self,draft,recipient_id,*,halted=None):
        """Exact historical lookup; never grants current recipient authority."""
        _permit(halted)
        scope=_scope(draft)
        _hash(recipient_id)
        row=self.db.execute("SELECT "+_READ_COLUMNS+"""
            FROM operator_recipients_v1 WHERE recipient_id=? AND plan_id=? AND draft_id=?""",
            (MAX_PAYLOAD,recipient_id,scope["plan_id"],scope["draft_id"])).fetchone()
        if row is None:
            return None
        data=_decode(row)
        _for_draft(draft,data["candidate"])
        return _view(data)
