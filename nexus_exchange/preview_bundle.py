"""Unsigned Windows preview bundle consistency and build provenance.

Build metadata and SHA-256 checks detect corruption/mismatch, not authenticity,
trusted publisher identity, signatures, legal readiness or release acceptance.
The diagnostic describes owned synthetic data only.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

FORMAT="nexus-windows-preview-bundle-v1"
MAX_EXE_BYTES=128*1024*1024
MAX_JSON_BYTES=65536
EXE="NexusExchange.exe"
CHECKSUM="SHA256.txt"
GENESIS="GENESIS.json"
MANIFEST="PREVIEW.json"
_EVENTS=("push","pull_request","workflow_dispatch")
_SMOKES=("self-test","gui-self-test","fixture-process-self-test","genesis-self-test")
_DIAGNOSTIC_FLAGS=("actual_opportunity_verified","requirements_verified","buyer_accepted",
    "contract_awarded","invoice_issued","payment_received","revenue_realized",
    "funds_available","zero_capital_verified","independently_verified",
    "execution_eligible","external_authority","reinvestment_authorized",
    "commercial_dispatch_enabled","release_eligible")
_REQUIRED_CHECKS=(
    "STARTUP_HALTED",
    "FIXTURE_DISCOVERY",
    "ARCHIVE_IDEMPOTENT",
    "CAPABILITY_FOCUS",
    "ZERO_EXPOSURE_MODEL",
    "DECLARED_STRUCTURE_ONLY",
    "COUNCIL_MISSING_EVIDENCE",
    "COUNCIL_REVIEW_ONLY",
    "COUNCIL_TERMINAL_NO_REPLAY",
    "CORRESPONDENCE_SCOPE_PINNED",
    "CORRESPONDENCE_REPLAY_DENIED",
    "ARTIFACT_EXACT_QA",
    "ACTUAL_LOCAL_ARTIFACT",
    "NO_OVERWRITE",
    "SCOPED_REVIEW_BOUND",
    "SCOPED_LOCAL_EXPORT",
    "SCOPED_OBLIGATION_PROVENANCE",
    "OBLIGATION_BOUND",
    "UNVERIFIED_ACCEPTANCE_NOTE",
    "INVOICE_TERMS_PINNED",
    "PARTIAL_RECONCILIATION",
    "DUPLICATE_AND_OVERPAYMENT_DENIED",
    "PARTIAL_ALLOCATION_HELD",
    "EMERGENCY_HALT_DENIES",
    "CORRESPONDENCE_BACKUP_INVENTORY",
    "VERIFIED_BACKUP_RESTORE",
    "RESTART_REQUIRES_RESUME",
    "DURABLE_CORRESPONDENCE_HISTORY",
    "RESTORED_CORRESPONDENCE_HISTORICAL_ONLY",
    "DURABLE_COUNCIL_AUDIT",
    "DURABLE_OBLIGATION_AND_RECEIPTS",
    "SCOPED_PROVENANCE_RECOVERED",
    "RESTORED_SCOPED_REVIEW_HISTORICAL_ONLY",
    "EXACT_SETTLEMENT",
    "FUTURE_RECEIPT_EXCLUDED",
    "PROTECTED_RESERVE_MODEL",
    "FINAL_LEDGER_STABLE",
)
_DIAGNOSTIC_IDS=("source_page_sha256","plan_id","capability_catalog_sha256",
    "council_report_sha256","correspondence_thread_id","correspondence_head_sha256",
    "artifact_sha256","qa_report_sha256","obligation_id","obligation_head_sha256",
    "scout_review_scope_sha256","scout_review_sha256","invoice_id",
    "receipt_head_sha256","allocation_sha256")
_FLAGS=("signed","publisher_authenticated","production_ready","release_eligible",
        "external_authority","actual_revenue_verified")


def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)


def _canonical(value):
    return (_json(value)+"\n").encode("ascii")


def _digest(data):
    return sha256(data).hexdigest()


def _hex(value,length):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{"+str(length)+"}",value):
        raise ValueError("invalid hexadecimal identity")
    return value


def _positive(value):
    if type(value) is not int or not 1<=value<=10**16:
        raise ValueError("invalid CI identifier")
    return value


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key]=value
    return result


def _constant(_value):
    raise ValueError("nonstandard JSON constant")


def _decode(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_JSON_BYTES:
        raise ValueError("preview metadata size")
    try:
        value=json.loads(raw.decode("ascii"),object_pairs_hook=_pairs,parse_constant=_constant)
        if type(value) is not dict or _canonical(value)!=raw:
            raise ValueError("noncanonical preview metadata")
    except (UnicodeError,ValueError,RecursionError,TypeError):
        raise ValueError("invalid preview metadata") from None
    return value


def _identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _read(path,maximum,*,retain=False,pe=False):
    """Bounded regular-file read and same-API stability checks."""
    try:
        initial=path.lstat()
        if not stat.S_ISREG(initial.st_mode) or not 1<=initial.st_size<=maximum:
            raise ValueError("invalid preview file size or type")
        flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
        fd=os.open(path,flags)
        try:
            before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_size!=initial.st_size
                    or (initial.st_ino and before.st_ino and
                        (initial.st_dev,initial.st_ino)!=(before.st_dev,before.st_ino))):
                raise ValueError("preview file changed")
            digest=sha256()
            content=bytearray()
            size=0
            first=True
            while True:
                chunk=os.read(fd,min(65536,maximum+1-size))
                if not chunk:
                    break
                if first and pe and not chunk.startswith(b"MZ"):
                    raise ValueError("missing Windows executable header")
                first=False
                size+=len(chunk)
                if size>maximum:
                    raise ValueError("preview file too large")
                digest.update(chunk)
                if retain:
                    content.extend(chunk)
            if (size!=initial.st_size or _identity(before)!=_identity(os.fstat(fd))
                    or _identity(initial)!=_identity(path.lstat())):
                raise ValueError("preview file changed")
        finally:
            os.close(fd)
    except OSError:
        raise ValueError("preview file unavailable") from None
    return dict(sha256=digest.hexdigest(),bytes=size),bytes(content) if retain else None


def _directory(value):
    path=Path(value)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("select extracted preview directory")
    return path


def _diagnostic(raw):
    data=_decode(raw)
    claimed=data.get("report_sha256")
    _hex(claimed,64)
    if (_digest(_json({k:v for k,v in data.items() if k!="report_sha256"}).encode("ascii"))!=claimed
            or data.get("format")!="nexus-owned-genesis-diagnostic-v1"
            or data.get("mode")!="OWNED_OFFLINE_FIXTURE_ONLY"
            or any(data.get(k) is not False for k in _DIAGNOSTIC_FLAGS)):
        raise ValueError("invalid owned Genesis diagnostic identity or authority")
    checks=data.get("checks")
    if type(checks) is not list or checks!=list(_REQUIRED_CHECKS):
        raise ValueError("incomplete or unexpected Genesis diagnostic sequence")
    for key in _DIAGNOSTIC_IDS:
        _hex(data.get(key),64)
    if data["correspondence_thread_id"]==data["correspondence_head_sha256"]:
        raise ValueError("invalid correspondence history identity")
    restored=data.get("restored_database_count")
    if type(restored) is not int or not 1<=restored<=64:
        raise ValueError("invalid restored database count")
    expected={"external_requests":0,"fixture_transport_calls":1,"council_attempts":2,
        "correspondence_event_count":1,
        "assumption_references":17,"independently_verified_assumptions":0,
        "modeled_pre_payment_exposure_cents":0,"modeled_probability_adjusted_net_cents":12000,
        "hypothetical_gross_cents":20000,"hypothetical_received_cents":20000,
        "hypothetical_outstanding_cents":0,"hypothetical_protected_reserve_cents":5000,
        "hypothetical_reinvestment_cents":15000}
    if any(type(data.get(k)) is not int or data[k]!=v for k,v in expected.items()):
        raise ValueError("unexpected owned Genesis diagnostic results")
    return claimed


def _build_identity(commit,tree,run_id,attempt,event):
    if type(event) is not str or event not in _EVENTS:
        raise ValueError("unsupported CI event")
    return dict(checkout_commit=_hex(commit,40),checkout_tree=_hex(tree,40),
                run_id=_positive(run_id),run_attempt=_positive(attempt),event=event)


def _manifest(identity,exe,genesis,report_sha):
    payload=dict(format=FORMAT,kind="UNSIGNED_PORTABLE_PREVIEW",platform="windows-x64",
        build=identity,executable=dict(name=EXE,**exe),
        source_diagnostic=dict(name=GENESIS,**genesis,report_sha256=report_sha),
        packaged_smoke_steps=list(_SMOKES),
        **dict.fromkeys(_FLAGS,False))
    return dict(payload,manifest_sha256=_digest(_json(payload).encode("ascii")))


def write_bundle(directory,*,commit,tree,run_id,attempt,event,diagnostic):
    """Called only after the CI smoke commands succeeded; do not overwrite metadata."""
    path=_directory(directory)
    identity=_build_identity(commit,tree,run_id,attempt,event)
    for name in (CHECKSUM,GENESIS,MANIFEST):
        if os.path.lexists(path/name):
            raise ValueError("preview metadata already exists")
    raw=_canonical(diagnostic)
    report_sha=_diagnostic(raw)
    exe,_=_read(path/EXE,MAX_EXE_BYTES,pe=True)
    manifest=_manifest(identity,exe,dict(sha256=_digest(raw),bytes=len(raw)),report_sha)
    for name,content in ((CHECKSUM,(exe["sha256"]+"\n").encode("ascii")),
                         (GENESIS,raw),(MANIFEST,_canonical(manifest))):
        with (path/name).open("xb") as handle:
            handle.write(content)
    return verify_bundle(path,expected_commit=commit,expected_tree=tree,expected_run=run_id,
                         expected_attempt=attempt,expected_event=event)


def verify_bundle(directory,*,expected_commit=None,expected_tree=None,expected_run=None,
                  expected_attempt=None,expected_event=None):
    """Validate exact bundle content and optional externally supplied build pins."""
    path=_directory(directory)
    _,raw_manifest=_read(path/MANIFEST,MAX_JSON_BYTES,retain=True)
    actual=_decode(raw_manifest)
    identity=actual.get("build")
    if type(identity) is not dict or set(identity)!={"checkout_commit","checkout_tree","run_id","run_attempt","event"}:
        raise ValueError("invalid preview build identity")
    identity=_build_identity(identity["checkout_commit"],identity["checkout_tree"],
                            identity["run_id"],identity["run_attempt"],identity["event"])
    if expected_commit is not None and identity["checkout_commit"]!=_hex(expected_commit,40):
        raise ValueError("checkout commit mismatch")
    if expected_tree is not None and identity["checkout_tree"]!=_hex(expected_tree,40):
        raise ValueError("checkout tree mismatch")
    if expected_run is not None and identity["run_id"]!=_positive(expected_run):
        raise ValueError("CI run mismatch")
    if expected_attempt is not None and identity["run_attempt"]!=_positive(expected_attempt):
        raise ValueError("CI run attempt mismatch")
    if expected_event is not None and (type(expected_event) is not str
            or expected_event not in _EVENTS or identity["event"]!=expected_event):
        raise ValueError("CI event mismatch")
    exe,_=_read(path/EXE,MAX_EXE_BYTES,pe=True)
    _,checksum=_read(path/CHECKSUM,65,retain=True)
    if checksum!=(exe["sha256"]+"\n").encode("ascii"):
        raise ValueError("executable checksum mismatch")
    genesis,raw_genesis=_read(path/GENESIS,MAX_JSON_BYTES,retain=True)
    report_sha=_diagnostic(raw_genesis)
    expected=_manifest(identity,exe,genesis,report_sha)
    if _canonical(actual)!=_canonical(expected):
        raise ValueError("preview manifest mismatch")
    return expected


def main():
    parser=argparse.ArgumentParser(description="Unsigned preview bundle consistency; not publisher authentication")
    sub=parser.add_subparsers(dest="operation",required=True)
    create=sub.add_parser("write")
    verify=sub.add_parser("verify")
    for command in (create,verify):
        command.add_argument("directory")
        command.add_argument("--commit",required=command is create)
        command.add_argument("--tree",required=command is create)
        command.add_argument("--run-id",type=int,required=command is create)
        command.add_argument("--attempt",type=int,required=command is create)
        command.add_argument("--event",choices=_EVENTS,required=command is create)
    args=parser.parse_args()
    if args.operation=="write":
        from .genesis_diagnostic import run_diagnostic
        result=write_bundle(args.directory,commit=args.commit,tree=args.tree,run_id=args.run_id,
                            attempt=args.attempt,event=args.event,diagnostic=run_diagnostic(confirmed=True))
    else:
        result=verify_bundle(args.directory,expected_commit=args.commit,
                             expected_tree=args.tree,expected_run=args.run_id,
                             expected_attempt=args.attempt,expected_event=args.event)
    print(_json(result))


if __name__=="__main__":
    main()
