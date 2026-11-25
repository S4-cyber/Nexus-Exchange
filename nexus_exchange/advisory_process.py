"""Fixed synthetic advisory child process, not an inference runtime or OS sandbox.

Only built-in code is dispatched. Shared slots are bounded; parent validates
all output after child exit. No tool execution, network or model weights.
"""
import json
import multiprocessing
import os
from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic_ns

from .local_advisory import (
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, _digest, _json, _parse_advice,
    _permit, build_request, review_response,
)

FIXTURE_MODEL_SHA256 = sha256(b"nexus-owned-advisory-fixture-v1;not-model-weights").hexdigest()
MAX_PARENT_MS = 15000
DEFAULT_PARENT_MS = 12000
_FLAGS = ("network_enabled", "model_executed", "dispatch_enabled",
          "external_authority", "independently_verified", "execution_eligible")
_REQUEST_FLAGS = ("independently_verified", "execution_eligible", "external_authority", "dispatch_enabled")
_REQUEST_FIELDS = {"format", "model_sha256", "attempt", "created_at", "snapshot_sha256",
                   "packet_sha256", "source_hold", "fields", "request_sha256", *_REQUEST_FLAGS}


class ProcessDenied(PermissionError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _check_halt(check):
    try:
        allowed = check() is False
    except Exception:
        allowed = False
    if not allowed:
        raise ProcessDenied("HALTED_OR_UNKNOWN")


def _request_bytes(request):
    # Private supervisor receives trusted projections only. Public entry point
    # constructs its request from the validated Council snapshot, not this hash.
    if (type(request) is not dict or set(request) != _REQUEST_FIELDS
            or request["format"] != "nexus-local-advice-request-v1"
            or request["model_sha256"] != FIXTURE_MODEL_SHA256
            or any(request[k] is not False for k in _REQUEST_FLAGS)
            or request["request_sha256"] != _digest({k:v for k,v in request.items() if k!="request_sha256"})):
        raise ValueError("exact synthetic advisory request required")
    raw = _json(request).encode("ascii")
    if not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise ValueError("advisory request size")
    return raw


def _worker(raw, buffer, length):
    """Deterministically echo known field states; no reasoning model is loaded."""
    try:
        request = json.loads(raw.decode("ascii"))
        if _request_bytes(request) != raw:
            raise ValueError("request encoding")
        advice = [dict(field=row["field"], reason=row["state"],
                       reference_id=row["reference_ids"][0] if row["reference_ids"] else None)
                  for row in request["fields"]]
        reply = _json(dict(format="nexus-local-advice-response-v1",
                           request_sha256=request["request_sha256"],
                           model_sha256=request["model_sha256"], advice=advice)).encode("ascii")
        if not 1 <= len(reply) <= MAX_RESPONSE_BYTES:
            raise ValueError("response size")
        buffer[:len(reply)] = reply
        length.value = len(reply)
    except Exception:
        raise SystemExit(1) from None


def _cleanup(process):
    if process.pid is not None:
        if process.is_alive():
            process.terminate()
            process.join(0.5)
        if process.is_alive():
            process.kill()
            process.join(0.5)
        if process.is_alive():
            raise ProcessDenied("WORKER_CLEANUP_FAILED")
        process.join(0)
    process.close()


def _supervise(request, *, halt_check, timeout_ms, target=_worker):
    """Private trusted failure-injection seam. Public caller cannot choose a target."""
    _check_halt(halt_check)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_PARENT_MS:
        raise ValueError("invalid advisory process budget")
    raw = _request_bytes(request)
    # Canonical copy so a caller cannot mutate the parent validation context.
    request = json.loads(raw.decode("ascii"))
    context = multiprocessing.get_context("spawn")
    buffer = context.RawArray("B", MAX_RESPONSE_BYTES)
    length = context.RawValue("i", 0)
    process = context.Process(target=target, args=(raw, buffer, length), daemon=True)
    start = monotonic_ns()
    deadline = start + timeout_ms * 1_000_000
    try:
        _check_halt(halt_check)
        try:
            process.start()
        except Exception:
            raise ProcessDenied("WORKER_START_FAILED") from None
        pid = process.pid
        if type(pid) is not int or pid <= 0 or pid == os.getpid():
            raise ProcessDenied("WORKER_ID")
        while True:
            _check_halt(halt_check)
            remaining = deadline - monotonic_ns()
            if remaining <= 0:
                raise ProcessDenied("WORKER_DEADLINE")
            process.join(min(remaining / 1_000_000_000, 0.025))
            if not process.is_alive():
                break
        _check_halt(halt_check)
        if monotonic_ns() >= deadline:
            raise ProcessDenied("WORKER_DEADLINE")
        if process.exitcode != 0:
            raise ProcessDenied("WORKER_EXIT_FAILED")
        size = length.value
        if type(size) is not int or not 1 <= size <= MAX_RESPONSE_BYTES:
            raise ProcessDenied("RESULT_SIZE")
        reply = bytes(buffer[:size])
        try:
            review = _parse_advice(reply, request)
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ProcessDenied("INVALID_RESPONSE") from None
        _check_halt(halt_check)
        elapsed = monotonic_ns() - start
        if elapsed < 0 or elapsed >= timeout_ms * 1_000_000:
            raise ProcessDenied("WORKER_DEADLINE")
        return dict(format="nexus-advisory-fixture-process-v1", worker_pid=pid,
                    child_process_completed=True, worker_exit_code=0,
                    parent_elapsed_ms=(elapsed+999999)//1000000, review=review,
                    response=reply, **dict.fromkeys(_FLAGS, False))
    finally:
        _cleanup(process)


def run_advisory_fixture(snapshot, *, approved=None, halt_check=None, clock=None):
    """One explicitly consented synthetic process; no persistent reservation.

    The caller supplies a trusted local snapshot. Future runtime integration
    must independently re-inspect its saved-plan scope and bind a durable
    reservation before launching any actual inference worker.
    """
    _check_halt(halt_check)
    _permit(approved, False)
    clock = clock or (lambda: datetime.now(timezone.utc))
    request = build_request(snapshot, FIXTURE_MODEL_SHA256, 1, now=clock(), approved=approved, halted=False)
    result = _supervise(request, halt_check=halt_check, timeout_ms=DEFAULT_PARENT_MS)
    _check_halt(halt_check)
    checked = review_response(result.pop("response"), request, snapshot, now=clock(),
                              approved=approved, halted=False)
    if _json(checked) != _json(result["review"]):
        raise ProcessDenied("INVALID_RESPONSE")
    _check_halt(halt_check)
    return dict(result, report_sha256=_digest(result))
