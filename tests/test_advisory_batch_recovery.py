import sqlite3
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_advisory_attempts as fixtures
from test_advisory_attempts import NOW, PLAN
from nexus_exchange.advisory_attempts import AdvisoryAttemptStore


class BatchRecoveryTests(unittest.TestCase):
    setUp = fixtures.AdvisoryAttemptTests.setUp
    reserve = fixtures.AdvisoryAttemptTests.reserve
    fail = fixtures.AdvisoryAttemptTests.fail

    def test_recover_all_preserves_terminal_records_and_escalates_third(self):
        with AdvisoryAttemptStore(self.path) as store:
            for _ in range(2):
                r = self.reserve(store)
                self.fail(store, r['ticket'])
            self.reserve(store)
            second = 'e' * 64
            self.snapshot['plan_id'] = second
            self.reserve(store)
            done = 'f' * 64
            self.snapshot['plan_id'] = done
            r = self.reserve(store)
            store.complete(r['ticket'], r['request'], self.snapshot,
                           b'owned fixture response', now=NOW, approved=True,
                           halted=False, worker_drained=True)
            self.assertEqual(store._runtime_pending(now=NOW), 2)
            self.assertEqual(store._runtime_recover_all(now=NOW), dict(recovered=2, escalated=1))
            self.assertEqual(store._runtime_pending(now=NOW), 0)
            self.assertEqual(store.status(PLAN, halted=False)['state'], 'ESCALATED')
            self.assertEqual(store.status(second, halted=False)['state'], 'INTERRUPTED')
            self.assertEqual(store.status(done, halted=False)['state'], 'REVIEWED')
            self.assertEqual(store._runtime_recover_all(now=NOW), dict(recovered=0, escalated=0))

    def test_batch_recovery_rolls_back_on_later_failure(self):
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            second = 'f' * 64
            self.snapshot['plan_id'] = second
            self.reserve(store)
            store.db.execute("CREATE TRIGGER reject_second BEFORE UPDATE ON advisory_attempts_v1 "
                             "WHEN OLD.plan_id='" + second + "' BEGIN SELECT RAISE(ABORT,'fixture'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store._runtime_recover_all(now=NOW)
            self.assertFalse(store.db.in_transaction)
            for plan in (PLAN, second):
                self.assertEqual(store.status(plan, halted=False)['state'], 'RESERVED')

    def test_batch_fails_closed_on_capacity_corruption_or_future_clock(self):
        with AdvisoryAttemptStore(self.path) as store:
            self.reserve(store)
            second = 'f' * 64
            self.snapshot['plan_id'] = second
            self.reserve(store, now=NOW + timedelta(seconds=1))
            with self.assertRaises(ValueError):
                store._runtime_recover_all(now=NOW)
            with patch('nexus_exchange.advisory_attempts.MAX_TASKS', 1):
                with self.assertRaises(ValueError):
                    store._runtime_pending(now=NOW + timedelta(seconds=1))
            self.assertEqual(store.status(PLAN, halted=False)['state'], 'RESERVED')
            store.db.execute("UPDATE advisory_attempts_v1 SET payload='{}' WHERE plan_id=?", (second,))
            with self.assertRaises(ValueError):
                store._runtime_recover_all(now=NOW + timedelta(seconds=1))
            self.assertEqual(store.status(PLAN, halted=False)['state'], 'RESERVED')
