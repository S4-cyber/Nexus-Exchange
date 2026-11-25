"""Supervise an owned Scout fixture in a fresh, bounded child process.

Only trusted, built-in Python code executes. This is process separation and
cleanup, NOT an OS security sandbox or a browser/network egress control.
"""
import json
import multiprocessing
import os
from hashlib import sha256
from time import monotonic_ns

from .browser_contract import (
    FIXTURES, FORMAT as TRACE_FORMAT, _digest, _permit, plan_fixture, validate_plan,
)
from .browser_fixture_runner import FORMAT as FIXTURE_FORMAT, _ASSETS, run_fixture

MAX_RESULT_BYTES = 8192
MAX_PARENT_MS = 15000
DEFAULT_PARENT_MS = 12000
_NS_PER_MS = 1_000_000
_FLAGS = ("independently_verified", "external_authority", "network_enabled",
          "dispatch_enabled", "browser_executed")


class ProcessDenied(PermissionError):
    """Only stable local reason codes; no child output or exception text."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _write_result(buffer, length, value):
    encoded = _canonical(value)
    if not 1 <= len(encoded) <= MAX_RESULT_BYTES:
        raise ValueError("RESULT_SIZE")
    buffer[:len(encoded)] = encoded
    # Parent reads only after normal child exit. No lock or blocking pipe.
    length.value = len(encoded)


def _worker(plan, buffer, length):
    """Fixed child entry point, no inputs beyond plan and bounded result slot."""
    try:
        report = run_fixture(plan, halted=False)
        _write_result(buffer, length, dict(pid=os.getpid(), report=report))
    except Exception:
        # Leave exit failure visible without leaking arbitrary exception text.
        raise SystemExit(1) from None


def _deny(reason):
    raise ProcessDenied(reason)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _hash(value):
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _check_object(value, fixed, variable):
    if type(value) is not dict or set(value) != set(fixed) | set(variable):
        _deny("RESULT_SCHEMA")
    if any(type(value[k]) is not type(v) or value[k] != v
           for k, v in fixed.items()):
        _deny("RESULT_SCOPE")


def _validate_report(report, plan):
    """Validate shape/scope, known asset hashes and canonical digests.

    Child timing and trace are self-reported, not independently authenticated.
    The parent independently observes process exit, not browser activity.
    """
    common = dict(fixture_id=plan["fixture_id"],
                  contract_sha256=plan["contract_sha256"],
                  **dict.fromkeys(_FLAGS, False))
    fixed = dict(common, format=FIXTURE_FORMAT, attempts=2,
                 result="OWNED_FIXTURE_COMPLETED")
    _check_object(report, fixed, ("elapsed_ms", "assets", "trace", "report_sha256"))
    if not _integer(report["elapsed_ms"], 0, plan["timeout_ms"]):
        _deny("RESULT_TIME")
    expected_assets = []
    for url, resource, media in FIXTURES[plan["fixture_id"]]:
        stored_media, body = _ASSETS[url]
        if stored_media != media:
            _deny("FIXTURE_ASSET_MISMATCH")
        expected_assets.append(dict(resource=resource, size=len(body),
                                    sha256=sha256(body).hexdigest()))
    if _canonical(report["assets"]) != _canonical(expected_assets):
        _deny("RESULT_ASSETS")
    trace = report["trace"]
    _check_object(trace, dict(common, format=TRACE_FORMAT, requests=2,
                             result="FIXTURE_TRACE_POLICY_MATCH"),
                  ("elapsed_ms", "trace_sha256", "report_sha256"))
    if not _integer(trace["elapsed_ms"], 0, report["elapsed_ms"]):
        _deny("RESULT_TIME")
    if not _hash(trace["trace_sha256"]):
        _deny("RESULT_DIGEST")
    for record in (trace, report):
        value = record["report_sha256"]
        if not _hash(value) or _digest({k: v for k, v in record.items()
                                       if k != "report_sha256"}) != value:
            _deny("RESULT_DIGEST")
    return report


def _read_result(buffer, length, pid, plan):
    size = length.value
    if not _integer(size, 1, MAX_RESULT_BYTES):
        _deny("RESULT_SIZE")
    raw = bytes(buffer[:size])
    try:
        value = json.loads(raw.decode("ascii"))
        if _canonical(value) != raw:
            _deny("RESULT_ENCODING")
        _check_object(value, dict(pid=pid), ("report",))
        return _validate_report(value["report"], plan)
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        _deny("RESULT_ENCODING")


def _check_halt(halt_check):
    try:
        allowed = halt_check() is False
    except Exception:
        allowed = False
    if not allowed:
        _deny("HALTED_OR_UNKNOWN")


def _cleanup(process):
    if process.pid is not None:
        if process.is_alive():
            process.terminate()
            process.join(0.5)
        if process.is_alive():
            process.kill()
            process.join(0.5)
        if process.is_alive():
            _deny("WORKER_CLEANUP_FAILED")
        process.join(0)
    process.close()


def _supervise(plan, *, halt_check, timeout_ms, target=_worker):
    """Internal test seam for trusted failure-injection targets only."""
    _check_halt(halt_check)
    plan = validate_plan(plan, halted=False)
    if plan["request_limit"] != 2 or not _integer(timeout_ms, 1, MAX_PARENT_MS):
        raise ValueError("INVALID_PROCESS_BUDGET")
    context = multiprocessing.get_context("spawn")
    buffer = context.RawArray("B", MAX_RESULT_BYTES)
    length = context.RawValue("i", 0)
    process = context.Process(target=target, args=(plan, buffer, length), daemon=True)
    start = monotonic_ns()
    deadline = start + timeout_ms * _NS_PER_MS
    try:
        _check_halt(halt_check)
        try:
            process.start()
        except Exception:
            _deny("WORKER_START_FAILED")
        pid = process.pid
        if not _integer(pid, 1, 2**63-1) or pid == os.getpid():
            _deny("WORKER_ID")
        while True:
            _check_halt(halt_check)
            remaining = deadline - monotonic_ns()
            if remaining <= 0:
                _deny("WORKER_DEADLINE")
            process.join(min(remaining / 1_000_000_000, 0.025))
            if not process.is_alive():
                break
        _check_halt(halt_check)
        if monotonic_ns() >= deadline:
            _deny("WORKER_DEADLINE")
        if process.exitcode != 0:
            _deny("WORKER_EXIT_FAILED")
        report = _read_result(buffer, length, pid, plan)
        _check_halt(halt_check)
        elapsed_ns = monotonic_ns() - start
        if elapsed_ns < 0 or elapsed_ns >= timeout_ms * _NS_PER_MS:
            _deny("WORKER_DEADLINE")
        payload = dict(format="nexus-fixture-process-v1",
                       fixture_id=plan["fixture_id"], worker_pid=pid,
                       child_process_completed=True, worker_exit_code=0,
                       parent_elapsed_ms=(elapsed_ns + _NS_PER_MS - 1) // _NS_PER_MS,
                       fixture_report=report, **dict.fromkeys(_FLAGS, False))
        return dict(payload, report_sha256=_digest(payload))
    finally:
        _cleanup(process)


def run_isolated_fixture(fixture_id, *, halted=None):
    """Standalone local diagnostic; never accepts a worker or a URL."""
    _permit(halted)
    plan = plan_fixture(fixture_id, request_limit=2, timeout_ms=5000, halted=halted)
    return _supervise(plan, halt_check=lambda: halted,
                      timeout_ms=DEFAULT_PARENT_MS)
