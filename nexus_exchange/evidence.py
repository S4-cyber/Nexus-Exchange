"""Aegis local evidence byte-integrity checks, not factual verification.

Files are read only on explicit owner selection. No document interpretation,
network access, path persistence, execution or commercial authorization.
"""
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
from .governor import Action, decide

MAX_BYTES=16*1024*1024
CHUNK_BYTES=64*1024
_PATTERN=re.compile(r"sha256:([0-9a-f]{64});bytes:([1-9][0-9]{0,8})")

class EvidenceError(ValueError):
    """Sanitized local evidence error; no path or file content."""

def _permit(halted,halt_check):
    if halt_check is not None and not callable(halt_check):
        raise PermissionError("HALT_STATE_UNKNOWN")
    live=halt_check() if halt_check is not None else False
    decision=decide(Action.RESEARCH_LOCAL,halted=False if halted is False and live is False else None)
    if not decision.allowed:
        raise PermissionError(decision.reason)

def parse_reference(value):
    if type(value) is not str:
        raise EvidenceError("INVALID_EVIDENCE_REFERENCE")
    match=_PATTERN.fullmatch(value)
    if match is None:
        raise EvidenceError("INVALID_EVIDENCE_REFERENCE")
    size=int(match.group(2))
    if not 1<=size<=MAX_BYTES:
        raise EvidenceError("EVIDENCE_SIZE_OUT_OF_BOUNDS")
    return match.group(1),size

def _identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def fingerprint(path,*,halted=None,halt_check=None):
    """Return a canonical hash/size reference; never retain the file or its name."""
    _permit(halted,halt_check)
    try:
        raw=os.fspath(path)
        if type(raw) is not str or not os.path.isabs(raw) or raw.startswith(("//","\\\\")):
            raise EvidenceError("SELECT_ABSOLUTE_LOCAL_FILE")
        selected=Path(raw)
        initial=selected.lstat()
        if not stat.S_ISREG(initial.st_mode):
            raise EvidenceError("EVIDENCE_NOT_REGULAR_FILE")
        if not 1<=initial.st_size<=MAX_BYTES:
            raise EvidenceError("EVIDENCE_SIZE_OUT_OF_BOUNDS")
        flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
        fd=os.open(selected,flags)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or _identity(before)!=_identity(initial):
                raise EvidenceError("EVIDENCE_FILE_CHANGED")
            digest=hashlib.sha256()
            size=0
            while True:
                _permit(halted,halt_check)
                block=os.read(fd,min(CHUNK_BYTES,MAX_BYTES+1-size))
                if not block:
                    break
                size+=len(block)
                if size>MAX_BYTES:
                    raise EvidenceError("EVIDENCE_SIZE_OUT_OF_BOUNDS")
                digest.update(block)
            after=os.fstat(fd)
            final=selected.lstat()
            if size!=before.st_size or _identity(before)!=_identity(after) or _identity(before)!=_identity(final):
                raise EvidenceError("EVIDENCE_FILE_CHANGED")
        finally:
            os.close(fd)
    except EvidenceError:
        raise
    except PermissionError:
        raise
    except (OSError,TypeError,ValueError,OverflowError):
        raise EvidenceError("EVIDENCE_FILE_UNAVAILABLE") from None
    _permit(halted,halt_check)
    return f"sha256:{digest.hexdigest()};bytes:{size}"

def verify_reference(path,reference,*,halted=None,halt_check=None):
    """Compare current file bytes with a previously recorded reference.

    A match proves byte equality to the recorded fingerprint, not document
    origin, authenticity, commercial terms or factual correctness.
    """
    _permit(halted,halt_check)
    parse_reference(reference)
    observed=fingerprint(path,halted=halted,halt_check=halt_check)
    same=hmac.compare_digest(reference,observed)
    return dict(status="BYTE_MATCH" if same else "BYTE_MISMATCH",
        byte_match=same,expected_reference=reference,observed_reference=observed,
        independently_verified=False,execution_eligible=False,external_authority=False)
