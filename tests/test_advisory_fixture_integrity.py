"""Synthetic worker protocol integrity and cleanup failure injection."""
import json
import multiprocessing
import unittest
from unittest.mock import Mock

from nexus_exchange.advisory_process import (
    FIXTURE_MODEL_SHA256, ProcessDenied, _cleanup, _supervise,
)
from nexus_exchange.local_advisory import _digest, _json


def request():
    payload = dict(format="nexus-local-advice-request-v1", model_sha256=FIXTURE_MODEL_SHA256,
                   attempt=1, created_at="2026-11-25T12:00:00.000000+00:00",
                   snapshot_sha256="a"*64, packet_sha256="b"*64,
                   source_hold="SOURCE_REVIEW_REQUIRED", fields=[
                       dict(field="cost:fixture", state="MISSING_REFERENCE", reference_ids=[]),
                       dict(field="price", state="REFERENCES_REQUIRE_VERIFICATION",
                            reference_ids=["c"*64, "d"*64])],
                   independently_verified=False, execution_eligible=False,
                   external_authority=False, dispatch_enabled=False)
    return dict(payload, request_sha256=_digest(payload))


def _altered(raw, buffer, length, mutation):
    req = json.loads(raw)
    rows = [dict(field=row["field"], reason=row["state"],
                 reference_id=row["reference_ids"][0] if row["reference_ids"] else None)
            for row in req["fields"]]
    if mutation == "partial":
        rows.pop()
    elif mutation == "alternate":
        rows[1]["reference_id"] = req["fields"][1]["reference_ids"][1]
    elif mutation == "reordered":
        rows.reverse()
    payload = dict(format="nexus-local-advice-response-v1", request_sha256=req["request_sha256"],
                   model_sha256=req["model_sha256"], advice=rows)
    reply = (json.dumps(payload) if mutation == "noncanonical" else _json(payload)).encode("ascii")
    buffer[:len(reply)] = reply
    length.value = len(reply)


def partial(raw, buffer, length):
    _altered(raw, buffer, length, "partial")


def alternate(raw, buffer, length):
    _altered(raw, buffer, length, "alternate")


def reordered(raw, buffer, length):
    _altered(raw, buffer, length, "reordered")


def noncanonical(raw, buffer, length):
    _altered(raw, buffer, length, "noncanonical")


class FixtureIntegrityTests(unittest.TestCase):
    def test_complete_fixed_reply_passes(self):
        result = _supervise(request(), halt_check=lambda: False, timeout_ms=12000)
        self.assertEqual(len(result["review"]["advice"]), 2)
        self.assertEqual(result["review"]["advice"][1]["reference_id"], "c"*64)
        self.assertFalse(result["external_authority"])

    def test_valid_but_wrong_fixture_replies_fail_after_child_exit(self):
        children = {p.pid for p in multiprocessing.active_children()}
        for target in (partial, alternate, reordered, noncanonical):
            with self.subTest(target=target.__name__):
                with self.assertRaises(ProcessDenied) as err:
                    _supervise(request(), halt_check=lambda: False, timeout_ms=12000, target=target)
                self.assertEqual(err.exception.reason, "INVALID_RESPONSE")
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, children)

    def test_cleanup_escalates_terminate_error_to_kill(self):
        process = Mock(pid=123, exitcode=-9)
        process.is_alive.side_effect = [True, True, False]
        process.terminate.side_effect = OSError("terminate failure")
        _cleanup(process)
        process.kill.assert_called_once_with()
        process.join.assert_any_call(0.5)
        process.join.assert_any_call(0)
        process.close.assert_called_once_with()

    def test_uncertain_cleanup_never_returns_success(self):
        for failure in ("kill", "join", "close", "exitcode", "still_alive"):
            with self.subTest(failure=failure):
                process = Mock(pid=123, exitcode=-9)
                process.is_alive.side_effect = [True, True, failure == "still_alive"]
                if failure in ("kill", "join", "close"):
                    getattr(process, failure).side_effect = OSError("cleanup failure")
                if failure == "exitcode":
                    process.exitcode = None
                with self.assertRaises(ProcessDenied) as err:
                    _cleanup(process)
                self.assertEqual(err.exception.reason, "WORKER_CLEANUP_FAILED")

    def test_unstarted_process_is_closed_without_join(self):
        process = Mock(pid=None)
        _cleanup(process)
        process.join.assert_not_called()
        process.close.assert_called_once_with()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
