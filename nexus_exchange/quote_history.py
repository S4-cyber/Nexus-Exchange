"""Bounded historical quotation receipts; not a current decision or permission."""
from copy import deepcopy
from datetime import datetime
import hashlib
import os
from pathlib import Path, PureWindowsPath
import tempfile

from .operator_drafts import _digest, _hash, _json, _stored_stamp
from .quote_comparison import _FLAGS

MAX_RECEIPT_BYTES = 64 * 1024


def _projection(result):
    if type(result) is not dict or result.get("format") != "nexus-synthetic-quote-comparison-v1":
        raise ValueError("reviewed synthetic comparison required")
    if result.get("mode") != "SIMULATION_ONLY" or any(result.get(k) is not False for k in _FLAGS):
        raise ValueError("historical authority mismatch")
    _stored_stamp(result.get("compared_at"))
    key = _hash(result.get("comparison_sha256"))
    payload = {k: v for k, v in result.items() if k != "comparison_sha256"}
    if _digest(_json(payload)) != key:
        raise ValueError("comparison digest mismatch")
    return _json({k: v for k, v in payload.items() if k != "compared_at"})


def historical_receipt(reviewed, current):
    """Both inputs must come from independently recomputed local comparisons.

    A digest is integrity metadata, not proof of authenticity. No raw reply
    content, recipient addresses, supplier profiles or filesystem paths added.
    """
    if _projection(reviewed) != _projection(current):
        raise ValueError("quotation evidence changed; review again")
    if datetime.fromisoformat(current["compared_at"]) < datetime.fromisoformat(reviewed["compared_at"]):
        raise ValueError("comparison clock moved backwards")
    payload = dict(format="nexus-historical-quote-review-v1",
                   historical_only=True, current_decision=False,
                   external_authority=False, execution_eligible=False,
                   rechecked_at=current["compared_at"],
                   rechecked_comparison_sha256=current["comparison_sha256"],
                   comparison=deepcopy(reviewed))
    return dict(payload, receipt_sha256=_digest(_json(payload)))


def publish_receipt(path, receipt, *, permit):
    """Publish closed, fsynced bytes under a new local JSON filename.

    No overwrite fallback. A halt after publication may leave a complete file
    without a returned success. Never remove the destination on failure.
    """
    permit()
    raw = os.fspath(path)
    if (type(raw) is not str or not os.path.isabs(raw) or len(raw) > 4096
            or raw.startswith(("//", "\\\\")) or any(ord(c) < 32 for c in raw)):
        raise ValueError("select an absolute local JSON path")
    target = Path(raw)
    if (target.suffix.lower() != ".json" or ".." in target.parts or ":" in target.name
            or PureWindowsPath(target.name).is_reserved()
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError("select a new JSON file in an existing direct directory")
    data = (_json(receipt) + "\n").encode("ascii")
    if not 1 <= len(data) <= MAX_RECEIPT_BYTES:
        raise ValueError("historical receipt exceeds export budget")
    temporary = None
    try:
        if os.path.lexists(target):
            raise FileExistsError("history destination exists")
        fd, name = tempfile.mkstemp(prefix=".nexus-quote-", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as output:
            permit()
            if output.write(data) != len(data):
                raise OSError("history write incomplete")
            output.flush()
            os.fsync(output.fileno())
        permit()
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink()
    permit()
    return hashlib.sha256(data).hexdigest()
