"""Exclusive, bounded local text export; no registration or transmission."""
import hashlib
import os
from pathlib import Path, PureWindowsPath

MAX_EXPORT_BYTES = 16 * 1024


def write_reviewed_text(path, body, *, permit):
    """Create a new file only, with exact UTF-8 bytes and no implicit overwrite.

    On a write/halt failure a partial or complete unregistered file can remain.
    Never delete a path on failure: it may have been replaced by another process.
    The caller must independently verify the fingerprint before registration.
    """
    permit()
    raw = os.fspath(path)
    if type(raw) is not str or not os.path.isabs(raw) or raw.startswith(('//', '\\\\')):
        raise ValueError('select an absolute local text file')
    target = Path(raw)
    if (target.suffix.lower() != '.txt' or ':' in target.name or
            PureWindowsPath(target.name).is_reserved() or
            any(ord(c) < 32 for c in target.name) or
            target.parent.resolve(strict=True) != target.parent):
        raise ValueError('select a new text file in an existing direct directory')
    if type(body) is not str or not body.startswith('LOCAL FOLLOW-UP DRAFT — DO NOT SEND\n'):
        raise ValueError('reviewed local follow-up required')
    data = body.encode('utf-8')
    if not 1 <= len(data) <= MAX_EXPORT_BYTES:
        raise ValueError('local follow-up exceeds export budget')
    permit()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, 'wb') as output:
        permit()
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    permit()
    return f'sha256:{hashlib.sha256(data).hexdigest()};bytes:{len(data)}'
