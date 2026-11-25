"""Explicit local CSV file boundaries for an owner-selected work sample.

Trusted local filesystem only. No network, arbitrary execution or path retention.
Atomic non-overwriting publication requires filesystem hard-link support.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile

from .digital_deliverable import (
    MAX_INPUT_BYTES,MAX_OUTPUT_BYTES,DeliverableError,_permit,_contract,CSV_SOURCE,JSON_SOURCE,_source_contract_format,
)
from .evidence import _identity,_same_file
from .lead_store import _digest,_json

_CHUNK=64*1024


def _path(value,*,source_format=CSV_SOURCE):
    _source_contract_format(source_format)
    suffix=".json" if source_format==JSON_SOURCE else ".csv"
    try:
        raw=os.fspath(value)
        if (type(raw) is not str or not os.path.isabs(raw)
                or raw.startswith(("//","\\\\")) or len(raw)>4096
                or any(ord(c)<32 for c in raw)):
            raise ValueError()
        path=Path(raw)
        if path.suffix.lower()!=suffix or ".." in path.parts:
            raise ValueError()
        # Deny Windows alternate data streams/device names.
        if os.name=="nt" and (":" in path.name or path.is_reserved()):
            raise ValueError()
        return path
    except (ValueError,TypeError,OverflowError):
        raise DeliverableError("SELECT_ABSOLUTE_LOCAL_JSON" if source_format==JSON_SOURCE else "SELECT_ABSOLUTE_LOCAL_CSV") from None


def read_selected_csv(value,*,halted=None,halt_check=None,source_format=CSV_SOURCE):
    return _read_local_file(value, source_format, MAX_INPUT_BYTES, halted, halt_check)


def read_published_csv(value, *, halted=None, halt_check=None):
    return _read_local_file(value, CSV_SOURCE, MAX_OUTPUT_BYTES, halted, halt_check)


def _read_local_file(value, source_format, maximum, halted, halt_check):
    _permit(halted,halt_check)
    path=_path(value,source_format=source_format)
    try:
        initial=path.lstat()
        if not stat.S_ISREG(initial.st_mode) or not 1<=initial.st_size<=maximum:
            raise DeliverableError("CSV_SOURCE_TYPE_OR_SIZE")
        flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
        fd=os.open(path,flags)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not _same_file(initial,before):
                raise DeliverableError("CSV_SOURCE_CHANGED")
            data=bytearray()
            while True:
                _permit(halted,halt_check)
                chunk=os.read(fd,min(_CHUNK,maximum+1-len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data)>maximum:
                    raise DeliverableError("CSV_SOURCE_TYPE_OR_SIZE")
            after=os.fstat(fd)
            final=path.lstat()
            if (len(data)!=before.st_size or _identity(before)!=_identity(after)
                    or _identity(initial)!=_identity(final) or not _same_file(final,after)):
                raise DeliverableError("CSV_SOURCE_CHANGED")
        finally:
            os.close(fd)
    except DeliverableError:
        raise
    except PermissionError:
        # Preserve a true halt, but sanitize filesystem path errors.
        _permit(halted,halt_check)
        raise DeliverableError("CSV_SOURCE_UNAVAILABLE") from None
    except (OSError,ValueError,TypeError,OverflowError):
        raise DeliverableError("CSV_SOURCE_UNAVAILABLE") from None
    _permit(halted,halt_check)
    return bytes(data)


def preview_pins(result):
    if type(result) is not dict or set(result)!={"contract","artifact","report"}:
        raise DeliverableError("INVALID_CSV_PREVIEW")
    contract=_contract(result["contract"])
    artifact=result["artifact"]
    report=result["report"]
    if (type(artifact) is not bytes or not 1<=len(artifact)<=MAX_OUTPUT_BYTES
            or type(report) is not dict or report.get("contract_sha256")!=contract["contract_sha256"]
            or report.get("plan_id")!=contract["plan_id"]
            or report.get("artifact_sha256")!=sha256(artifact).hexdigest()
            or report.get("report_sha256")!=_digest(_json({k:v for k,v in report.items() if k!="report_sha256"}))
            or report.get("local_criteria_passed") is not True):
        raise DeliverableError("INVALID_CSV_PREVIEW")
    from .digital_deliverable import _FLAGS
    if any(report.get(k) is not False for k in _FLAGS):
        raise DeliverableError("INVALID_CSV_PREVIEW")
    return dict(expected_contract=contract["contract_sha256"],
                expected_report=report["report_sha256"],expected_artifact=report["artifact_sha256"])


def publish_new_csv(value,artifact,*,halted=None,halt_check=None):
    """Write closed/fsynced temp bytes, then atomically link to an unused name.

    No overwrite fallback. A halt after publication may leave a complete file;
    no report is returned on a later halt. Never delete the destination.
    """
    _permit(halted,halt_check)
    path=_path(value)
    if type(artifact) is not bytes or not 1<=len(artifact)<=MAX_OUTPUT_BYTES:
        raise DeliverableError("CSV_OUTPUT_LIMIT")
    temporary=None
    try:
        # lstat sees even broken symlinks; link itself also rejects existing names.
        if os.path.lexists(path):
            raise DeliverableError("CSV_DESTINATION_EXISTS")
        fd,name=tempfile.mkstemp(prefix=".nexus-csv-",suffix=".tmp",dir=path.parent)
        temporary=Path(name)
        with os.fdopen(fd,"wb") as handle:
            for offset in range(0,len(artifact),_CHUNK):
                _permit(halted,halt_check)
                chunk=artifact[offset:offset+_CHUNK]
                if handle.write(chunk)!=len(chunk):
                    raise DeliverableError("CSV_OUTPUT_WRITE_FAILED")
            handle.flush()
            os.fsync(handle.fileno())
        _permit(halted,halt_check)
        os.link(temporary,path)
    except DeliverableError:
        raise
    except FileExistsError:
        raise DeliverableError("CSV_DESTINATION_EXISTS") from None
    except PermissionError:
        _permit(halted,halt_check)
        raise DeliverableError("CSV_OUTPUT_UNAVAILABLE") from None
    except (OSError,ValueError,TypeError,OverflowError):
        raise DeliverableError("CSV_OUTPUT_UNAVAILABLE") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                raise DeliverableError("CSV_TEMP_CLEANUP_FAILED_CHECK_DESTINATION") from None
    _permit(halted,halt_check)
