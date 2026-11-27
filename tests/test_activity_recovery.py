"""Local activity write faults must hold autonomous engagement."""
import sqlite3
import unittest

from nexus_exchange.cycle_recovery import CycleMaintenanceRequired, CycleRecovery


class ActivityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE activity(state TEXT)')
        self.db.execute('CREATE TABLE journal(state TEXT)')
        self.calls = []
        self.halted = False
        self.recovery = CycleRecovery(self.settle, self.record, lambda: self.halted)
        self.recovery.record('queued')
        self.recovery.record('running')

    def settle(self, failed):
        self.calls.append(('settle', failed))
        self.db.execute("UPDATE activity SET state='Stopped'")

    def record(self, state):
        self.calls.append(('journal', state))
        self.db.execute('INSERT INTO journal VALUES (?)', (state,))

    def write(self):
        self.calls.append(('write',))
        return self.db.execute("INSERT INTO activity VALUES ('Pending')").rowcount

    def test_successful_write_preserves_result(self):
        self.assertEqual(self.recovery.write_activity(self.write), 1)
        self.assertEqual(self.db.execute('SELECT state FROM activity').fetchall(), [('Pending',)])

    def test_database_rejection_holds_and_terminalizes_without_repeating_write(self):
        self.db.execute("CREATE TRIGGER reject BEFORE INSERT ON activity BEGIN SELECT RAISE(ABORT, 'private fixture'); END")
        with self.assertRaises(CycleMaintenanceRequired) as original:
            self.recovery.write_activity(self.write)
        self.assertNotIn('private fixture', str(original.exception))
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(original.exception)
        self.assertEqual(self.calls, [('journal', 'queued'), ('journal', 'running'),
                                      ('write',), ('settle', True), ('journal', 'failed')])
        self.assertEqual(self.db.execute('SELECT state FROM activity').fetchall(), [])

    def test_validation_and_filesystem_errors_are_sanitized(self):
        for kind in (ValueError, OSError, PermissionError, sqlite3.OperationalError):
            with self.subTest(kind=kind):
                def reject():
                    raise kind('private fixture')
                with self.assertRaises(CycleMaintenanceRequired) as error:
                    self.recovery.write_activity(reject)
                self.assertNotIn('private fixture', str(error.exception))

    def test_unexpected_programming_error_is_not_reclassified(self):
        def broken():
            raise TypeError('fixture')
        with self.assertRaises(TypeError):
            self.recovery.write_activity(broken)

    def test_halt_during_write_failure_still_requires_maintenance(self):
        def reject():
            self.halted = True
            raise sqlite3.OperationalError('private fixture')
        with self.assertRaises(CycleMaintenanceRequired) as original:
            self.recovery.write_activity(reject)
        with self.assertRaises(CycleMaintenanceRequired):
            self.recovery.fail(original.exception)
        self.assertEqual(self.calls[-2:], [('settle', False), ('journal', 'cancelled')])


if __name__ == '__main__':
    unittest.main()
