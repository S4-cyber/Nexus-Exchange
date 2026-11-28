"""Real child-process termination at local report/journal boundaries."""
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from nexus_exchange.cycle_history import BRIEF, CycleHistory, latest
from nexus_exchange.cycle_journal import describe_outcome
from nexus_exchange.event_store import EventStore, read_projection

STAMP = '2026-11-26T12:00:00+00:00'
OLD_ID = 'a' * 32
NEW_ID = 'b' * 32
CHILD = r'''
import os
import sys
from pathlib import Path
from nexus_exchange.cycle_history import CycleHistory, latest
from nexus_exchange.event_store import EventStore
root, mode, stamp, key = sys.argv[1:]
root = Path(root)
store = EventStore(root / 'events.sqlite3')
base = dict(task_id=key, target='Autonomous Scout cycle', timestamp=stamp)
for state in ('queued', 'running'):
    store.append(dict(base, state=state))
brief = dict(latest(root), cycle_id=key, notes=['new'])
if mode == 'before':
    os.replace = lambda *args: os._exit(73)
digest = CycleHistory(store.db).publish(root, brief, lambda: None)
if mode == 'terminal':
    store.append(dict(base, state='succeeded', report_sha256=digest))
os._exit(73)
'''


class PublicationCrashTests(unittest.TestCase):
    def test_process_exit_before_replace_after_publish_and_after_terminal(self):
        for mode in ('before', 'after', 'terminal'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                prior = dict(format='nexus-engagement-brief-v1', cycle_id=OLD_ID,
                             status='Completed', finished=STAMP, jobs={},
                             notes=['old'], sources=[], shortlist=[], external_actions=0)
                store = EventStore(root / 'events.sqlite3')
                try:
                    event = dict(task_id=OLD_ID, target='Autonomous Scout cycle', timestamp=STAMP)
                    for state in ('queued', 'running'):
                        store.append(dict(event, state=state))
                    digest = CycleHistory(store.db).publish(root, prior, lambda: None)
                    store.append(dict(event, state='succeeded', report_sha256=digest))
                finally:
                    store.close()
                child = subprocess.run([sys.executable, '-c', CHILD, str(root), mode, STAMP, NEW_ID],
                                       cwd=Path(__file__).resolve().parents[1],
                                       capture_output=True, timeout=30)
                self.assertEqual(child.returncode, 73, child.stderr.decode(errors='replace'))
                reopened = EventStore(root / 'events.sqlite3')
                try:
                    history = CycleHistory(reopened.db)
                    current = latest(root)
                    self.assertEqual(current['cycle_id'], OLD_ID if mode == 'before' else NEW_ID)
                    self.assertEqual(history.read(digest), prior)
                    self.assertEqual(reopened.read()[-1]['state'], 'succeeded' if mode == 'terminal' else 'running')
                    now = datetime(2026, 11, 26, 12, 1, tzinfo=timezone.utc)
                    self.assertEqual(reopened.recover_interrupted(now=now), int(mode != 'terminal'))
                    self.assertEqual(reopened.recover_interrupted(now=now), 0)
                    records = reopened.read()
                    self.assertEqual(records[-1]['state'], 'succeeded' if mode == 'terminal' else 'interrupted')
                    if mode == 'terminal':
                        self.assertEqual(records[-1]['report_sha256'], sha256((root / BRIEF).read_bytes()).hexdigest())
                    else:
                        self.assertNotIn('report_sha256', records[-1])
                    outcome = describe_outcome(current, lambda: read_projection(reopened.db)['history'])
                    if mode == 'after':
                        self.assertIn('interrupted', outcome)
                        self.assertIn('completion unconfirmed', outcome)
                    else:
                        self.assertIn('report digest matches', outcome)
                    self.assertEqual(describe_outcome(prior, lambda: read_projection(reopened.db)['history']),
                                     'Journal: succeeded (report digest matches; local evidence only)')
                finally:
                    reopened.close()


if __name__ == '__main__':
    unittest.main()
