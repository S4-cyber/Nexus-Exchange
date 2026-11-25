import multiprocessing
import os
import time
import unittest
from unittest.mock import patch

from nexus_exchange.advisory_process import (
    FIXTURE_MODEL_SHA256, MAX_RESPONSE_BYTES, ProcessDenied, _supervise, _worker,
)
from nexus_exchange.local_advisory import _digest, _json


def request():
    payload = dict(format="nexus-local-advice-request-v1", model_sha256=FIXTURE_MODEL_SHA256,
                   attempt=1, created_at="2026-11-25T12:00:00.000000+00:00",
                   snapshot_sha256="a"*64, packet_sha256="b"*64,
                   source_hold="SOURCE_REVIEW_REQUIRED", fields=[
                       dict(field="cost:fixture", state="MISSING_REFERENCE", reference_ids=[]),
                       dict(field="price", state="REFERENCES_REQUIRE_VERIFICATION", reference_ids=["c"*64])],
                   independently_verified=False, execution_eligible=False,
                   external_authority=False, dispatch_enabled=False)
    return dict(payload, request_sha256=_digest(payload))


def stall(raw, buffer, length):
    time.sleep(30)


def exit_bad(raw, buffer, length):
    raise SystemExit(7)


def oversize(raw, buffer, length):
    length.value = MAX_RESPONSE_BYTES + 1


def empty(raw, buffer, length):
    return


def forged(raw, buffer, length):
    import json
    req = json.loads(raw)
    reply = _json(dict(format="nexus-local-advice-response-v1", request_sha256=req["request_sha256"],
                       model_sha256=req["model_sha256"], advice=[dict(field="price",
                           reason="REFERENCES_REQUIRE_VERIFICATION", reference_id="e"*64)])).encode("ascii")
    buffer[:len(reply)] = reply
    length.value = len(reply)


class AdvisoryProcessTests(unittest.TestCase):
    def setUp(self):
        self.children = {p.pid for p in multiprocessing.active_children()}

    def tearDown(self):
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, self.children)

    def supervise(self, target=_worker, **kwargs):
        options = dict(halt_check=lambda: False, timeout_ms=12000, target=target)
        options.update(kwargs)
        return _supervise(request(), **options)

    def test_spawned_fixture_response_is_review_only(self):
        result = self.supervise()
        self.assertNotEqual(result["worker_pid"], os.getpid())
        self.assertTrue(result["child_process_completed"])
        self.assertEqual(result["worker_exit_code"], 0)
        self.assertEqual(result["review"]["source_hold"], "SOURCE_REVIEW_REQUIRED")
        self.assertEqual(result["review"]["unresolved_fields"], ["cost:fixture"])
        self.assertEqual(result["review"]["advice"][1]["reference_id"], "c"*64)
        for key in ("network_enabled", "model_executed", "dispatch_enabled", "external_authority", "independently_verified"):
            self.assertIs(result[key], False)

    def test_deadline_terminates_stalled_child(self):
        start = time.monotonic()
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(stall, timeout_ms=250)
        self.assertEqual(err.exception.reason, "WORKER_DEADLINE")
        self.assertLess(time.monotonic()-start, 8)

    def test_halt_during_supervision_cleans_child(self):
        calls = 0
        def halt():
            nonlocal calls
            calls += 1
            return calls >= 4
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(stall, halt_check=halt)
        self.assertEqual(err.exception.reason, "HALTED_OR_UNKNOWN")

    def test_failed_exit_missing_and_oversized_output(self):
        for target, reason in ((exit_bad,"WORKER_EXIT_FAILED"),(empty,"RESULT_SIZE"),(oversize,"RESULT_SIZE")):
            with self.subTest(target=target.__name__), self.assertRaises(ProcessDenied) as err:
                self.supervise(target)
            self.assertEqual(err.exception.reason, reason)

    def test_fabricated_reference_rejected_after_child_exit(self):
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(forged)
        self.assertEqual(err.exception.reason, "INVALID_RESPONSE")

    def test_bad_budget_halt_and_altered_request_denied_before_spawn(self):
        with patch("nexus_exchange.advisory_process.multiprocessing.get_context") as ctx:
            for budget in (True,0,15001):
                with self.assertRaises(ValueError):
                    self.supervise(timeout_ms=budget)
            for halted in (True,None,0):
                with self.assertRaises(ProcessDenied):
                    self.supervise(halt_check=lambda: halted)
            changed = dict(request(), model_sha256="d"*64)
            changed["request_sha256"] = _digest({k:v for k,v in changed.items() if k!="request_sha256"})
            with self.assertRaises(ValueError):
                _supervise(changed, halt_check=lambda: False, timeout_ms=12000)
            ctx.assert_not_called()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
