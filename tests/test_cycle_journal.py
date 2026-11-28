"""Read-only cycle correlation never confers authority or rewrites history."""
import sqlite3
from types import SimpleNamespace
import unittest

from nexus_exchange.cycle_journal import describe_outcome

ID = 'a' * 32
TARGET = 'Autonomous Scout cycle'
START = '2026-11-26T12:00:00+00:00'
FINISH = '2026-11-26T12:01:00+00:00'
END = '2026-11-26T12:02:00+00:00'


def event(state, stamp=END, target=TARGET, task=ID):
    return SimpleNamespace(task_id=task, target=target, state=state, timestamp=stamp)


class CycleJournalTests(unittest.TestCase):
    def setUp(self):
        self.brief = dict(cycle_id=ID, finished=FINISH, status='Completed')
        self.started = [event('queued', START), event('running', START)]

    def outcome(self, history):
        return describe_outcome(self.brief, lambda: history)

    def test_legacy_and_invalid_id_do_not_read_journal(self):
        def unexpected():
            self.fail('unlinked report must not query journal')
        self.assertIn('legacy', describe_outcome({}, unexpected))
        for value in (None, '', 'A'*32, 'x'*32, ['a'], 'a'*33):
            with self.subTest(value=value):
                self.assertIn('invalid', describe_outcome(dict(cycle_id=value), unexpected))

    def test_success_and_failure_correlate_without_certifying_contents(self):
        self.assertEqual(self.outcome(self.started + [event('succeeded')]),
                         'Journal: succeeded (cycle ID match only)')
        self.brief['status'] = 'Sources unavailable'
        self.assertEqual(self.outcome(self.started + [event('failed')]),
                         'Journal: failed (cycle ID match only)')

    def test_interrupted_or_cancelled_publication_is_not_success(self):
        for state in ('interrupted', 'cancelled', 'running', 'queued'):
            with self.subTest(state=state):
                history = self.started + [event(state)] if state in ('interrupted','cancelled') else self.started[:1 if state == 'queued' else 2]
                self.assertEqual(self.outcome(history), f'Journal: {state} — completion unconfirmed')

    def test_no_match_or_wrong_target(self):
        self.assertIn('no matching', self.outcome([event('succeeded', task='b'*32)]))
        self.assertIn('target mismatch', self.outcome([event('succeeded', target='Manual work')]))

    def test_disagreement_and_timing_are_explicit(self):
        self.assertIn('status mismatch', self.outcome(self.started + [event('failed')]))
        self.assertIn('timing mismatch', self.outcome(self.started + [event('succeeded', START)]))
        self.brief['finished'] = '2026-11-26T11:59:00+00:00'
        self.assertIn('timing mismatch', self.outcome(self.started + [event('succeeded')]))
        self.brief['finished'] = 'invalid'
        self.assertIn('timing mismatch', self.outcome(self.started + [event('succeeded')]))

    def test_journal_read_failure_is_redacted(self):
        for error in (ValueError('private'), sqlite3.DatabaseError('private'), OSError('private')):
            with self.subTest(error=type(error)):
                def unavailable():
                    raise error
                result = describe_outcome(self.brief, unavailable)
                self.assertEqual(result, 'Journal: unavailable — completion unconfirmed')
                self.assertNotIn('private', result)

    def test_unrelated_later_task_does_not_override_cycle(self):
        self.assertEqual(self.outcome(self.started + [event('succeeded'), event('failed', task='b'*32)]),
                         'Journal: succeeded (cycle ID match only)')


if __name__ == '__main__':
    unittest.main()
