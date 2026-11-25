import multiprocessing
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from nexus_exchange.advisory_process import run_advisory_fixture, ProcessDenied
from nexus_exchange.local_advisory import TTL, _digest
from test_context_packet import snapshot, NOW


class AdvisoryFixtureIntegrationTests(unittest.TestCase):
    def test_actual_council_snapshot_reviewed_after_child_exit(self):
        children={p.pid for p in multiprocessing.active_children()}
        s=snapshot(held=True,reference=True)
        report=run_advisory_fixture(s,approved=True,halt_check=lambda:False,clock=lambda:NOW)
        self.assertNotEqual(report["worker_pid"],os.getpid())
        self.assertTrue(report["child_process_completed"])
        self.assertEqual(report["worker_exit_code"],0)
        self.assertEqual(report["review"]["source_hold"],"SOURCE_REVIEW_REQUIRED")
        self.assertEqual(report["review"]["unresolved_fields"],[])
        self.assertEqual(len(report["review"]["advice"]),s["total"])
        for advice in report["review"]["advice"]:
            self.assertIn(advice["reference_id"],s["reference_ids"][advice["field"]])
        self.assertNotIn("response",report)
        self.assertFalse(report["model_executed"])
        self.assertFalse(report["external_authority"])
        self.assertEqual(report["report_sha256"],_digest({k:v for k,v in report.items()
                                                          if k!="report_sha256"}))
        self.assertEqual({p.pid for p in multiprocessing.active_children()},children)

    def test_no_consent_or_bad_snapshot_never_spawns(self):
        with patch("nexus_exchange.advisory_process.multiprocessing.get_context") as ctx:
            for approved in (None,False,1):
                with self.assertRaises(PermissionError):
                    run_advisory_fixture(snapshot(),approved=approved,
                                         halt_check=lambda:False,clock=lambda:NOW)
            with self.assertRaises(ProcessDenied):
                run_advisory_fixture(snapshot(),approved=True,halt_check=lambda:None,clock=lambda:NOW)
            s=snapshot()
            s["snapshot_sha256"]="0"*64
            with self.assertRaises(ValueError):
                run_advisory_fixture(s,approved=True,halt_check=lambda:False,clock=lambda:NOW)
            ctx.assert_not_called()

    def test_expired_at_collection_never_returns_advice(self):
        children={p.pid for p in multiprocessing.active_children()}
        times=iter([NOW,NOW+TTL+timedelta(microseconds=1)])
        with self.assertRaises(ValueError):
            run_advisory_fixture(snapshot(),approved=True,
                                 halt_check=lambda:False,clock=lambda:next(times))
        self.assertEqual({p.pid for p in multiprocessing.active_children()},children)


if __name__=="__main__":
    multiprocessing.freeze_support()
    unittest.main()
