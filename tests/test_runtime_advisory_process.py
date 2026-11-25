"""Owner lifecycle regression using a saved synthetic scenario and real child."""
import unittest
from datetime import timedelta
from time import monotonic, sleep
from unittest.mock import patch

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore, DB_NAME
from nexus_exchange.advisory_process import ProcessDenied
from nexus_exchange.runtime_guard import RuntimeGuard
from test_scenario_council import ScenarioCouncilTests


class RuntimeAdvisoryProcessTests(unittest.TestCase):
    def setUp(self):
        fixture=ScenarioCouncilTests("test_inspection_is_not_an_attempt")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.fixture=fixture
        self.directory=fixture.directory
        self.key=fixture.key
        self.now=fixture.now

    def guard(self):
        return RuntimeGuard(self.directory,clock=lambda:self.now)

    def state(self):
        with AdvisoryAttemptStore(self.directory/DB_NAME,existing_only=True) as store:
            return store.status(self.key,halted=False)

    def collect(self,guard):
        deadline=monotonic()+20
        while monotonic()<deadline:
            result=guard.poll_advisory_process()
            if result is not None:
                return result
            sleep(0.01)
        self.fail("synthetic advisory supervisor did not finish")

    def test_real_child_and_fresh_scope_completion(self):
        with self.guard() as guard:
            guard.resume()
            for value in (None,False,1):
                with self.assertRaises(PermissionError):
                    guard.start_advisory_process(self.key,confirmed=value)
            self.assertFalse((self.directory/DB_NAME).exists())
            ticket=guard.start_advisory_process(self.key,confirmed=True)
            try:
                self.assertEqual(ticket["attempt"],1)
                self.assertEqual(self.state()["state"],"RESERVED")
                self.assertTrue(guard.advisory_process_pending())
                self.assertTrue(guard.status()["advisory_cleanup_unconfirmed"])
                with self.assertRaises(PermissionError):
                    guard.close()
                with self.assertRaises(PermissionError):
                    guard.council_action("inspect",self.key)
                self.now+=timedelta(microseconds=100)
                result=self.collect(guard)
                self.assertEqual(result["state"],"REVIEWED")
                self.assertFalse(result["review"]["external_authority"])
                self.assertFalse(guard.advisory_process_pending())
                self.assertFalse(guard.status()["advisory_cleanup_unconfirmed"])
                self.assertEqual(self.state()["attempts_used"],1)
            finally:
                if guard.advisory_process_pending():
                    guard.set()
                    guard.drain_advisory_process()

    def test_halt_withholds_result_and_consumes_reservation_only_on_recovery(self):
        with self.guard() as guard:
            guard.resume()
            guard.start_advisory_process(self.key,confirmed=True)
            try:
                guard.set()
                with self.assertRaises(PermissionError):
                    guard.recover_advisory()
                with self.assertRaises(PermissionError):
                    guard.resume()
            finally:
                guard.drain_advisory_process()
            self.assertEqual(self.state()["state"],"RESERVED")
            self.assertFalse(guard.status()["advisory_cleanup_unconfirmed"])
            self.assertEqual(guard.recover_advisory()["recovered"],1)
            self.assertEqual(self.state()["state"],"INTERRUPTED")
            guard.resume()
            self.assertFalse(guard.is_set())

    def test_cleanup_uncertainty_blocks_same_session_recovery(self):
        with self.guard() as guard:
            guard.resume()
            with patch("nexus_exchange.advisory_process._supervise",
                       side_effect=ProcessDenied("WORKER_CLEANUP_FAILED")):
                guard.start_advisory_process(self.key,confirmed=True)
                try:
                    with self.assertRaises(ProcessDenied):
                        self.collect(guard)
                finally:
                    if guard.advisory_process_pending():
                        guard.set()
                        guard.drain_advisory_process()
            self.assertTrue(guard.is_set())
            self.assertEqual(self.state()["state"],"RESERVED")
            with self.assertRaises(PermissionError):
                guard.recover_advisory()
            with self.assertRaises(PermissionError):
                guard.resume()
            self.assertTrue(guard.status()["advisory_cleanup_unconfirmed"])
        # An ordinary application restart must not erase uncertain cleanup.
        with self.guard() as restarted:
            self.assertTrue(restarted.is_set())
            self.assertTrue(restarted.status()["advisory_cleanup_unconfirmed"])
            self.assertEqual(self.state()["state"],"RESERVED")
            with self.assertRaises(PermissionError):
                restarted.recover_advisory()
            with self.assertRaises(PermissionError):
                restarted.resume()

    def test_failed_submission_quarantines_before_worker_launch(self):
        with self.guard() as guard:
            guard.resume()
            with patch("nexus_exchange.runtime_guard.ThreadPoolExecutor.submit",
                       side_effect=RuntimeError("synthetic submission fault")):
                with self.assertRaises(RuntimeError):
                    guard.start_advisory_process(self.key,confirmed=True)
            self.assertTrue(guard.status()["advisory_cleanup_unconfirmed"])
            self.assertFalse(guard.advisory_process_pending())
            self.assertEqual(self.state()["state"],"RESERVED")
        with self.guard() as restarted:
            self.assertTrue(restarted.status()["advisory_cleanup_unconfirmed"])
            with self.assertRaises(PermissionError):
                restarted.resume()
            self.assertEqual(self.state()["state"],"RESERVED")

    def test_scope_change_withholds_result(self):
        with self.guard() as guard:
            guard.resume()
            guard.start_advisory_process(self.key,confirmed=True)
            try:
                self.fixture.attach_all()
                with self.assertRaises(ValueError):
                    self.collect(guard)
                self.assertTrue(guard.is_set())
                self.assertEqual(self.state()["state"],"RESERVED")
                self.assertEqual(guard.recover_advisory()["recovered"],1)
            finally:
                if guard.advisory_process_pending():
                    guard.set()
                    guard.drain_advisory_process()
