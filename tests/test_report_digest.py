"""Local report evidence, with real journal and filesystem fixtures."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from nexus_exchange.cycle_history import BRIEF, CycleHistory, encode, latest
from nexus_exchange.cycle_journal import describe_outcome
from nexus_exchange.cycle_recovery import CycleRecovery, CycleMaintenanceRequired
from nexus_exchange.event_store import EventStore, read_projection

ID = 'a' * 32
TARGET = 'Autonomous Scout cycle'
START = '2026-11-26T12:00:00.000000+00:00'
END = '2026-11-26T12:02:00.000000+00:00'


def event(state, **extra):
    return dict(task_id=ID, target=TARGET, state=state,
                timestamp=END if state in ('succeeded', 'failed') else START, **extra)


class ReportDigestTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.store = EventStore(self.directory / 'events.sqlite3')
        self.addCleanup(self.store.close)
        self.archive = CycleHistory(self.store.db)
        self.brief = dict(format='nexus-engagement-brief-v1', cycle_id=ID,
                          status='Completed', finished='2026-11-26T12:01:00+00:00',
                          notes=['fixture'], sources=[], shortlist=[], jobs={})
        self.store.append(event('queued'))
        self.store.append(event('running'))

    def outcome(self, brief):
        return describe_outcome(brief, lambda: read_projection(self.store.db)['history'])

    def publish(self):
        recovery = CycleRecovery(lambda failed: None, lambda state: None, lambda: False)
        return recovery.publish(lambda check: self.archive.publish(self.directory, self.brief, check))

    def test_publish_returns_digest_of_actual_canonical_bytes(self):
        self.assertEqual(self.publish(), sha256((self.directory / BRIEF).read_bytes()).hexdigest())

    def test_round_trip_and_content_change(self):
        digest = sha256(encode(self.brief)).hexdigest()
        self.store.append(event('succeeded', report_sha256=digest))
        self.assertEqual(self.store.read()[-1]['report_sha256'], digest)
        self.store.close()
        self.store = EventStore(self.directory / 'events.sqlite3')
        self.addCleanup(self.store.close)
        self.assertEqual(self.outcome(self.brief), 'Journal: succeeded (report digest matches; local evidence only)')
        changed = dict(self.brief, notes=['modified'])
        self.assertIn('digest mismatch', self.outcome(changed))

    def test_failed_published_report_can_be_bound(self):
        self.brief['status'] = 'Sources unavailable'
        digest = sha256(encode(self.brief)).hexdigest()
        self.store.append(event('failed', report_sha256=digest))
        self.assertEqual(self.outcome(self.brief), 'Journal: failed (report digest matches; local evidence only)')

    def test_legacy_terminal_remains_id_only(self):
        self.store.append(event('succeeded'))
        self.assertEqual(self.outcome(self.brief), 'Journal: succeeded (cycle ID match only)')

    def test_invalid_digest_metadata_rejected_without_mutation(self):
        before = self.store.read()
        valid = event('succeeded', report_sha256='b'*64)
        cases = [dict(valid, report_sha256=x) for x in (None, 1, '', 'B'*64, 'g'*64, 'b'*65)]
        cases += [dict(valid, state='cancelled'), dict(valid, state='interrupted'),
                  dict(valid, task_id='other'), dict(valid, target='Manual work'),
                  dict(valid, extra='field')]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.store.append(bad)
            self.assertEqual(self.store.read(), before)

    def test_publication_failure_returns_no_evidence(self):
        self.publish()
        before = latest(self.directory)
        self.brief['notes'] = ['new']
        with patch('nexus_exchange.cycle_history.os.replace', side_effect=OSError('private')):
            with self.assertRaises(CycleMaintenanceRequired):
                self.publish()
        self.assertEqual(latest(self.directory), before)
        self.assertNotIn('report_sha256', self.store.read()[-1])

    def test_terminal_digest_capacity_reserved_at_running_admission(self):
        terminal = event('succeeded', report_sha256='b'*64)
        size = sum(len(json.dumps(e, sort_keys=True).encode('utf-8'))
                   for e in (event('queued'), event('running'), terminal))
        self.store.db.execute('DELETE FROM events')
        with patch('nexus_exchange.event_store.MAX_JOURNAL_BYTES', size-1):
            self.store.append(event('queued'))
            with self.assertRaisesRegex(ValueError, 'byte capacity'):
                self.store.append(event('running'))
        self.assertEqual(self.store.read(), (event('queued'),))
        with patch('nexus_exchange.event_store.MAX_JOURNAL_BYTES', size):
            self.store.append(event('running'))
            self.store.append(terminal)
        self.assertEqual(self.store.read()[-1], terminal)

    def test_interrupted_running_task_never_invents_digest(self):
        self.publish()
        self.assertEqual(self.store.recover_interrupted(now=datetime(2026, 11, 26, 12, 3, tzinfo=timezone.utc)), 1)
        self.assertNotIn('report_sha256', self.store.read()[-1])
        self.assertIn('interrupted', self.outcome(latest(self.directory)))


if __name__ == '__main__':
    unittest.main()
