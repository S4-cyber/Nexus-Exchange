"""Publication failures pause Scout while explicit halt remains cancellation."""
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nexus_exchange.cycle_history import BRIEF, CycleHistory, encode
from nexus_exchange.cycle_recovery import CycleMaintenanceRequired, CycleRecovery


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.db = sqlite3.connect(self.directory / 'events.sqlite3', isolation_level=None)
        self.addCleanup(self.db.close)
        self.history = CycleHistory(self.db)
        self.old = self.brief('old')
        self.history.publish(self.directory, self.old, lambda: None)
        self.db.execute('CREATE TABLE journal(state TEXT NOT NULL)')
        self.calls = []
        self.halted = False
        self.recovery = CycleRecovery(self.calls.append, self.record, lambda: self.halted)
        self.recovery.record('queued')
        self.recovery.record('running')
        self.recovery.settle()

    def brief(self, note):
        return dict(format='nexus-engagement-brief-v1', finished='2026-11-26T08:00:00+00:00',
                    status='Completed', notes=[note], sources=[], shortlist=[], jobs={})

    def record(self, state):
        self.db.execute('INSERT INTO journal VALUES (?)', (state,))

    def states(self):
        return [r[0] for r in self.db.execute('SELECT state FROM journal ORDER BY rowid')]

    def publish(self):
        try:
            self.recovery.publish(lambda check: CycleHistory(self.db).publish(
                self.directory, self.brief('new'), check))
        except Exception as error:
            self.recovery.fail(error)
            raise
        self.recovery.record('succeeded')

    def preserved(self):
        self.assertEqual((self.directory / BRIEF).read_bytes(), encode(self.old))
        self.assertEqual(self.calls, [False])
        self.assertFalse(self.db.in_transaction)
        self.assertFalse(list(self.directory.glob('.cycle-*.tmp')))

    def test_archive_rejection_requires_maintenance(self):
        self.db.execute('CREATE TRIGGER skip BEFORE INSERT ON cycle_briefs BEGIN SELECT RAISE(IGNORE); END')
        with self.assertRaises(CycleMaintenanceRequired):
            self.publish()
        self.preserved()
        self.assertEqual(self.states(), ['queued', 'running', 'failed'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM cycle_briefs').fetchone(), (0,))

    def test_filesystem_permission_error_is_not_a_halt(self):
        with patch('nexus_exchange.cycle_history.os.replace', side_effect=PermissionError('private fixture')):
            with self.assertRaises(CycleMaintenanceRequired) as error:
                self.publish()
        self.assertNotIn('private fixture', str(error.exception))
        self.preserved()
        self.assertEqual(self.states()[-1], 'failed')

    def test_constructor_schema_error_requires_maintenance(self):
        self.db.execute('DROP TABLE cycle_briefs')
        self.db.execute('CREATE TABLE cycle_briefs(wrong TEXT)')
        with self.assertRaises(CycleMaintenanceRequired):
            self.publish()
        self.preserved()
        self.assertEqual(self.states()[-1], 'failed')

    def test_explicit_halt_is_cancellation_not_maintenance(self):
        self.halted = True
        with self.assertRaises(PermissionError):
            self.publish()
        self.preserved()
        self.assertEqual(self.states()[-1], 'cancelled')

    def test_halt_inside_archive_rolls_back(self):
        states = iter((False, True))
        self.recovery._stopped = lambda: next(states, False)
        with self.assertRaises(PermissionError):
            self.publish()
        self.preserved()
        self.assertEqual(self.states()[-1], 'cancelled')
        self.assertEqual(self.db.execute('SELECT count(*) FROM cycle_briefs').fetchone(), (0,))

    def test_healthy_publication_keeps_previous_and_terminalizes(self):
        self.publish()
        self.assertEqual((self.directory / BRIEF).read_bytes(), encode(self.brief('new')))
        self.assertEqual(self.states()[-1], 'succeeded')
        self.assertEqual(self.calls, [False])
        self.assertEqual(self.db.execute('SELECT count(*) FROM cycle_briefs').fetchone(), (1,))

    def test_unexpected_programming_fault_is_not_classified_as_storage(self):
        with patch.object(CycleHistory, 'publish', side_effect=RuntimeError('fixture')):
            with self.assertRaisesRegex(RuntimeError, '^fixture$'):
                self.publish()
        self.preserved()
        self.assertEqual(self.states()[-1], 'failed')


if __name__ == '__main__':
    unittest.main()
