import multiprocessing
import os
import time
import unittest
from unittest.mock import patch

from nexus_exchange.browser_contract import plan_fixture, _digest
from nexus_exchange.browser_fixture_runner import run_fixture
from nexus_exchange.browser_process import (
    MAX_RESULT_BYTES, ProcessDenied, _supervise, _write_result,
    run_isolated_fixture,
)


def _stall(plan, buffer, length):
    time.sleep(30)


def _exit_bad(plan, buffer, length):
    raise SystemExit(9)


def _missing(plan, buffer, length):
    return


def _oversized(plan, buffer, length):
    length.value = MAX_RESULT_BYTES + 1


def _wrong_pid(plan, buffer, length):
    _write_result(buffer, length, dict(pid=0, report=run_fixture(plan, halted=False)))


def _altered_authority(plan, buffer, length):
    report = run_fixture(plan, halted=False)
    report["external_authority"] = True
    report["report_sha256"] = _digest({k: v for k, v in report.items()
                                       if k != "report_sha256"})
    _write_result(buffer, length, dict(pid=os.getpid(), report=report))


def _altered_asset(plan, buffer, length):
    report = run_fixture(plan, halted=False)
    report["assets"][0]["sha256"] = "0" * 64
    report["report_sha256"] = _digest({k: v for k, v in report.items()
                                       if k != "report_sha256"})
    _write_result(buffer, length, dict(pid=os.getpid(), report=report))


class BrowserProcessTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_fixture("procurement", request_limit=2,
                                 timeout_ms=5000, halted=False)
        self.children = {p.pid for p in multiprocessing.active_children()}

    def tearDown(self):
        self.assertEqual({p.pid for p in multiprocessing.active_children()},
                         self.children, "fixture worker leaked")

    def supervise(self, target, timeout_ms=12000, halt_check=lambda: False):
        return _supervise(self.plan, halt_check=halt_check,
                          timeout_ms=timeout_ms, target=target)

    def test_real_spawn_both_fixtures(self):
        for name in ("procurement", "digital_services"):
            result = run_isolated_fixture(name, halted=False)
            self.assertEqual(result["fixture_id"], name)
            self.assertTrue(result["child_process_completed"])
            self.assertNotEqual(result["worker_pid"], os.getpid())
            self.assertEqual(result["worker_exit_code"], 0)
            self.assertEqual(result["fixture_report"]["attempts"], 2)
            self.assertLessEqual(result["parent_elapsed_ms"], 12000)
            for flag in ("independently_verified", "external_authority",
                         "dispatch_enabled", "network_enabled", "browser_executed"):
                self.assertIs(result[flag], False)

    def test_halt_and_unknown_id_before_spawn(self):
        with patch("nexus_exchange.browser_process.multiprocessing.get_context") as ctx:
            for halted in (None, True, 0):
                with self.assertRaises(PermissionError):
                    run_isolated_fixture("procurement", halted=halted)
            with self.assertRaises(ValueError):
                run_isolated_fixture("https://example.com/", halted=False)
            ctx.assert_not_called()

    def test_timeout_terminates_stalled_worker(self):
        start = time.monotonic()
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_stall, timeout_ms=250)
        self.assertEqual(err.exception.reason, "WORKER_DEADLINE")
        self.assertLess(time.monotonic() - start, 8)

    def test_halt_mid_supervision_terminates_worker(self):
        calls = 0
        def halt():
            nonlocal calls
            calls += 1
            return calls >= 4
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_stall, halt_check=halt)
        self.assertEqual(err.exception.reason, "HALTED_OR_UNKNOWN")
        self.assertGreaterEqual(calls, 4)

    def test_bad_exit_not_success(self):
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_exit_bad)
        self.assertEqual(err.exception.reason, "WORKER_EXIT_FAILED")

    def test_empty_and_oversized_results(self):
        for target in (_missing, _oversized):
            with self.subTest(target=target.__name__), self.assertRaises(ProcessDenied) as err:
                self.supervise(target)
            self.assertEqual(err.exception.reason, "RESULT_SIZE")

    def test_wrong_process_identity(self):
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_wrong_pid)
        self.assertEqual(err.exception.reason, "RESULT_SCOPE")

    def test_authority_tampering_even_with_recomputed_hash(self):
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_altered_authority)
        self.assertEqual(err.exception.reason, "RESULT_SCOPE")

    def test_asset_tampering_even_with_recomputed_hash(self):
        with self.assertRaises(ProcessDenied) as err:
            self.supervise(_altered_asset)
        self.assertEqual(err.exception.reason, "RESULT_ASSETS")

    def test_invalid_parent_budgets_before_spawn(self):
        with patch("nexus_exchange.browser_process.multiprocessing.get_context") as ctx:
            for budget in (0, True, 15001):
                with self.assertRaises(ValueError):
                    self.supervise(_stall, timeout_ms=budget)
            ctx.assert_not_called()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
