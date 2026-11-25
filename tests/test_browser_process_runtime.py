import tempfile
import unittest
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.browser_process import ProcessDenied


class BrowserProcessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.guard=RuntimeGuard(Path(self.tmp.name))
        self.addCleanup(self.cleanup_guard)

    def cleanup_guard(self):
        if not self.guard._closed:
            self.guard.set()
            self.guard.drain_browser_process()
            self.guard.close()

    def wait(self):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            report=self.guard.poll_browser_process()
            if report is not None:
                return report
            time.sleep(.01)
        self.fail("fixture did not finish")

    def start(self,name="procurement"):
        self.guard.start_browser_process(name,confirmed=True)

    def test_real_process_under_owner_guard(self):
        self.guard.resume()
        self.start()
        self.assertTrue(self.guard.browser_process_pending())
        report=self.wait()
        self.assertTrue(report["child_process_completed"])
        self.assertFalse(report["external_authority"])
        self.assertFalse(self.guard.browser_process_pending())
        self.assertFalse(self.guard._browser_active)
        self.assertEqual(len(self.guard.events.read()),0)

    def test_startup_confirmation_and_scope(self):
        with self.assertRaises(PermissionError):
            self.start()
        self.guard.resume()
        with patch("nexus_exchange.browser_process._supervise") as supervisor:
            for confirmed in (None,False,1,"true"):
                with self.assertRaises(PermissionError):
                    self.guard.start_browser_process("procurement",confirmed=confirmed)
            with self.assertRaises(ValueError):
                self.start("https://example.com/")
            supervisor.assert_not_called()
        self.assertFalse(self.guard.browser_process_pending())

    def test_owner_thread_required(self):
        self.guard.resume()
        with ThreadPoolExecutor(max_workers=1) as worker:
            for fn in (self.start,self.guard.poll_browser_process,
                       self.guard.browser_process_pending,self.guard.drain_browser_process):
                with self.assertRaises(PermissionError):
                    worker.submit(fn).result(timeout=5)

    def test_active_journal_and_council_reservation_deny(self):
        self.guard.resume()
        stamp=lambda:self.guard._clock().isoformat()
        self.guard.events.append(dict(task_id="x",target="synthetic",state="queued",
                                      timestamp=stamp()))
        try:
            with self.assertRaises(PermissionError):
                self.start()
        finally:
            self.guard.events.append(dict(task_id="x",target="synthetic",state="cancelled",
                                          timestamp=stamp()))
        with patch.object(self.guard,"_council_pending",return_value=1):
            with self.assertRaises(PermissionError):
                self.start()
        self.assertTrue(self.guard.is_set())
        self.assertFalse(self.guard.browser_process_pending())

    def test_pending_blocks_reentry_close_and_resume(self):
        self.guard.resume()
        entered=threading.Event()
        released=threading.Event()
        def blocked(*args,**kwargs):
            entered.set()
            released.wait(5)
            return {"synthetic":True}
        with patch("nexus_exchange.browser_process._supervise",side_effect=blocked):
            self.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertIsNone(self.guard.poll_browser_process())
                for fn in (self.start,self.guard.resume,self.guard.close,
                           lambda:self.guard.browser_fixture("procurement",confirmed=True),
                           lambda:self.guard.council_action("inspect","x"),
                           lambda:self.guard.operator_action("history","x",draft_id="x")):
                    with self.assertRaises(PermissionError):
                        fn()
                self.guard.set()
                with self.assertRaises(PermissionError):
                    self.guard.resume()
            finally:
                released.set()
                self.guard.drain_browser_process()
        self.assertFalse(self.guard.browser_process_pending())
        self.assertTrue(self.guard.is_set())
        self.guard.resume()
        self.assertFalse(self.guard.is_set())

    def test_halt_before_collection_suppresses_even_completed_report(self):
        self.guard.resume()
        with patch("nexus_exchange.browser_process._supervise",return_value={"synthetic":True}):
            self.start()
            self.guard._browser_job.result(timeout=5)
            self.guard.set()
            self.assertTrue(self.guard.browser_process_pending())
            with self.assertRaises(PermissionError):
                self.guard.poll_browser_process()
        self.assertFalse(self.guard.browser_process_pending())
        self.assertTrue(self.guard.is_set())

    def test_actual_process_immediate_halt_and_drain(self):
        self.guard.resume()
        self.start("digital_services")
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.guard.resume()
        self.guard.drain_browser_process()
        self.assertFalse(self.guard.browser_process_pending())
        self.assertTrue(self.guard.is_set())
        self.guard.resume()

    def test_unexpected_failure_requires_halt_and_no_retry(self):
        self.guard.resume()
        with patch("nexus_exchange.browser_process._supervise",
                   side_effect=RuntimeError("synthetic")) as supervisor:
            self.start()
            with self.assertRaises(RuntimeError):
                self.wait()
            self.assertEqual(supervisor.call_count,1)
        self.assertTrue(self.guard.is_set())
        self.assertFalse(self.guard.browser_process_pending())

    def test_cleanup_failure_latches_fault(self):
        self.guard.resume()
        with patch("nexus_exchange.browser_process._supervise",
                   side_effect=ProcessDenied("WORKER_CLEANUP_FAILED")):
            self.start()
            with self.assertRaises(ProcessDenied):
                self.wait()
        self.assertTrue(self.guard.is_set())
        with self.assertRaises(PermissionError):
            self.guard.resume()

    def test_drain_requires_halt_and_poll_requires_reservation(self):
        self.guard.resume()
        with self.assertRaises(PermissionError):
            self.guard.drain_browser_process()
        with self.assertRaises(PermissionError):
            self.guard.poll_browser_process()


if __name__=="__main__":
    unittest.main()
