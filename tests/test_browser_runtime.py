import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.browser_fixture_runner import FixtureDenied, _load_asset
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.governor import Action, decide


class BrowserRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.guard = RuntimeGuard(Path(self.tmp.name))
        self.addCleanup(self.guard.close)

    def run_fixture(self, name="procurement"):
        return self.guard.browser_fixture(name, confirmed=True)

    def test_startup_and_explicit_confirmation(self):
        with self.assertRaises(PermissionError):
            self.run_fixture()
        self.guard.resume()
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            for value in (None, False, 1, "yes"):
                with self.subTest(value=value), self.assertRaises(PermissionError):
                    self.guard.browser_fixture("procurement", confirmed=value)
            with self.assertRaises(ValueError):
                self.run_fixture("https://example.com/")
            load.assert_not_called()
        self.assertFalse(self.guard.is_set())

    def test_real_guard_both_fixtures_no_external_authority(self):
        self.guard.resume()
        for name in ("procurement", "digital_services"):
            report = self.run_fixture(name)
            self.assertEqual(report["fixture_id"], name)
            self.assertEqual(report["attempts"], 2)
            for flag in ("external_authority", "dispatch_enabled",
                         "network_enabled", "browser_executed", "independently_verified"):
                self.assertIs(report[flag], False)
        self.assertEqual(len(self.guard.events.read()), 0)
        self.assertFalse(decide(Action.FETCH_EXTERNAL, halted=False).allowed)

    def test_owner_thread_only(self):
        self.guard.resume()
        with ThreadPoolExecutor(max_workers=1) as worker:
            with self.assertRaises(PermissionError):
                worker.submit(self.run_fixture).result(timeout=5)
        self.assertFalse(self.guard.is_set())

    def test_active_journal_blocks_diagnostic(self):
        self.guard.resume()
        self.guard.events.append(dict(task_id="fixture", target="synthetic",
                                      state="queued", timestamp=self.guard._clock().isoformat()))
        try:
            with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
                with self.assertRaises(PermissionError):
                    self.run_fixture()
                load.assert_not_called()
        finally:
            self.guard.events.append(dict(task_id="fixture", target="synthetic",
                                          state="cancelled", timestamp=self.guard._clock().isoformat()))

    def test_reentry_and_close_refused_while_running(self):
        self.guard.resume()
        def load(url):
            with self.assertRaises(PermissionError):
                self.run_fixture()
            with self.assertRaises(PermissionError):
                self.guard.resume()
            with self.assertRaises(PermissionError):
                self.guard.close()
            with self.assertRaises(PermissionError):
                self.guard.council_action("inspect", "synthetic")
            with self.assertRaises(PermissionError):
                self.guard.operator_action("history", "synthetic", draft_id="synthetic")
            return _load_asset(url)
        with patch("nexus_exchange.browser_fixture_runner._load_asset", side_effect=load):
            self.assertEqual(self.run_fixture()["attempts"], 2)
        self.assertFalse(self.guard._browser_active)

    def test_halt_during_asset_read_withholds_output_and_next_lookup(self):
        self.guard.resume()
        def load(url):
            self.guard.set()
            return _load_asset(url)
        with patch("nexus_exchange.browser_fixture_runner._load_asset", side_effect=load) as mock:
            with self.assertRaises(FixtureDenied):
                self.run_fixture()
            self.assertEqual(mock.call_count, 1)
        self.assertTrue(self.guard.is_set())
        self.assertEqual(self.guard.status()["reason"], "emergency")
        self.assertFalse(self.guard._browser_active)
        with self.assertRaises(PermissionError):
            self.run_fixture()
        self.guard.resume()
        self.assertEqual(self.run_fixture()["attempts"], 2)

    def test_unexpected_failure_halts_without_retry(self):
        self.guard.resume()
        with patch("nexus_exchange.browser_fixture_runner._load_asset",
                   side_effect=RuntimeError("synthetic")) as mock:
            with self.assertRaises(RuntimeError):
                self.run_fixture()
            self.assertEqual(mock.call_count, 1)
        self.assertTrue(self.guard.is_set())
        self.assertEqual(self.guard.status()["reason"], "emergency")
        self.assertFalse(self.guard._browser_active)

    def test_outstanding_council_reservation_blocks_before_asset(self):
        self.guard.resume()
        with patch.object(self.guard, "_council_pending", return_value=1):
            with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
                with self.assertRaises(PermissionError):
                    self.run_fixture()
                load.assert_not_called()
        self.assertTrue(self.guard.is_set())

    def test_result_suppressed_if_halt_after_completion(self):
        from nexus_exchange.browser_fixture_runner import _run_fixture
        self.guard.resume()
        def complete(*args, **kwargs):
            report = _run_fixture(*args, **kwargs)
            self.guard.set()
            return report
        with patch("nexus_exchange.browser_fixture_runner._run_fixture", side_effect=complete):
            with self.assertRaises(PermissionError):
                self.run_fixture()
        self.assertTrue(self.guard.is_set())
        self.assertFalse(self.guard._browser_active)

    def test_faulted_runtime_never_loads(self):
        self.guard.resume()
        with patch.object(self.guard, "_persist", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                self.guard.set()
        with patch("nexus_exchange.browser_fixture_runner._load_asset") as load:
            with self.assertRaises(PermissionError):
                self.run_fixture()
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
