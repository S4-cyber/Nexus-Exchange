"""Fault-injection tests for independent Scout terminalization."""
import sqlite3
import unittest
from nexus_exchange.cycle_recovery import CycleRecovery, CycleMaintenanceRequired


class CycleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE journal(state TEXT NOT NULL)')
        self.db.execute('CREATE TABLE activity(state TEXT NOT NULL)')
        self.db.execute("INSERT INTO activity VALUES ('Engaged')")
        self.calls = []
        self.halted = False
        self.recovery = CycleRecovery(self.settle, self.record, lambda: self.halted)

    def settle(self, failed):
        self.calls.append(('settle', failed))
        self.db.execute('UPDATE activity SET state=?', ('Failed' if failed else 'Stopped',))

    def record(self, state):
        self.calls.append(('journal', state))
        self.db.execute('INSERT INTO journal VALUES (?)', (state,))

    def running(self):
        self.recovery.record('queued')
        self.recovery.record('running')

    def history(self):
        return [row[0] for row in self.db.execute('SELECT state FROM journal ORDER BY rowid')]

    def test_interruption_settlement_failure_still_terminalizes_journal(self):
        self.running()
        self.db.execute("CREATE TRIGGER bad BEFORE UPDATE ON activity BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired) as error:
            self.recovery.fail(RuntimeError('original error'))
        self.assertNotIn('private fixture', str(error.exception))
        self.assertEqual(self.history(), ['queued', 'running', 'failed'])
        self.assertEqual(self.db.execute('SELECT state FROM activity').fetchone(), ('Engaged',))

    def test_normal_settlement_failure_is_not_retried(self):
        self.running()
        self.db.execute("CREATE TRIGGER bad BEFORE UPDATE ON activity BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired) as original:
            self.recovery.settle()
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(original.exception)
        self.assertEqual(self.calls.count(('settle', False)), 1)
        self.assertEqual(self.calls.count(('settle', True)), 0)
        self.assertEqual(self.history()[-1], 'failed')

    def test_cancellation_preserves_terminal_state_despite_settlement_failure(self):
        self.running()
        self.halted = True
        self.db.execute("CREATE TRIGGER bad BEFORE UPDATE ON activity BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(PermissionError('cancelled'))
        self.assertEqual(self.history()[-1], 'cancelled')

    def test_journal_failure_is_not_retried_but_settlement_is_attempted(self):
        self.running()
        self.db.execute("CREATE TRIGGER bad BEFORE INSERT ON journal BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired) as original:
            self.recovery.record('succeeded')
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(original.exception)
        self.assertEqual(self.history(), ['queued', 'running'])
        self.assertEqual(self.calls, [('journal', 'queued'), ('journal', 'running'), ('journal', 'succeeded'), ('settle', True)])

    def test_journal_terminalization_failure_escalates(self):
        self.running()
        self.db.execute("CREATE TRIGGER bad BEFORE INSERT ON journal BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(RuntimeError('original error'))
        self.assertEqual(self.history(), ['queued', 'running'])
        self.assertEqual(self.calls[-1], ('journal', 'failed'))

    def test_healthy_failure_does_not_escalate(self):
        self.running()
        self.recovery.fail(RuntimeError('source error'))
        self.assertEqual(self.history()[-1], 'failed')
        self.assertEqual(self.calls[-2:], [('settle', True), ('journal', 'failed')])

    def test_queued_failure_uses_valid_interrupted_transition(self):
        self.recovery.record('queued')
        self.recovery.fail(RuntimeError('before start'))
        self.assertEqual(self.history(), ['queued', 'interrupted'])

    def test_settled_cycle_is_not_settled_again_after_publish_error(self):
        self.running()
        self.recovery.settle()
        self.recovery.fail(OSError('publish error'))
        self.assertEqual(self.calls[-2:], [('settle', False), ('journal', 'failed')])

    def test_initial_journal_failure_does_not_invent_a_terminal_task(self):
        self.db.execute("CREATE TRIGGER bad BEFORE INSERT ON journal BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired) as original:
            self.recovery.record('queued')
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(original.exception)
        self.assertEqual(self.history(), [])
        self.assertEqual(self.calls, [('journal', 'queued'), ('settle', True)])


if __name__ == '__main__':
    unittest.main()
