import tempfile
import unittest
from pathlib import Path

from nexus_exchange.advisory_attempts import AdvisoryAttemptStore
from nexus_exchange.advisory_history_pin import build_history_pin
from nexus_exchange.advisory_process import FIXTURE_MODEL_SHA256, _supervise
from nexus_exchange.council_history_context import build_council_history_context
from nexus_exchange.local_advisory import build_request, _digest, _json
from test_context_packet import NOW, PLAN, snapshot
from test_quote_history_reviewed import comparison, historical


def project(snap, rows):
    stamp = snap['evaluated_at']
    context = build_council_history_context(PLAN, limit=1, confirmed=True,
        inspect=lambda: snap, compare=lambda: comparison(stamp),
        read_history=lambda: rows, permit=lambda: None, clock=lambda: NOW)
    return build_history_pin(context, snap, halted=False)


class AdvisoryHistoryIntegrationTests(unittest.TestCase):
    def test_history_bound_fixture_and_durable_review_reject_hidden_drift(self):
        snap = snapshot(held=True)
        older = dict(historical(), receipt_sha256='1'*64)
        newest = dict(historical(), rechecked_at=snap['evaluated_at'])
        original = project(snap, [older, newest])
        fresh = project(snap, [newest, older])
        drift = project(snap, [dict(older, receipt_sha256='2'*64), newest])
        self.assertEqual(original, fresh)
        self.assertNotEqual(original['scope_history_sha256'], drift['scope_history_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            with AdvisoryAttemptStore(Path(directory)/'advice.sqlite3') as store:
                reserved = store.reserve(snap, FIXTURE_MODEL_SHA256, now=NOW,
                    approved=True, halted=False, history_pin=original)
                request, ticket = reserved['request'], reserved['ticket']
                self.assertEqual(request['history_pin'], original)
                self.assertEqual(request['fields'], build_request(snap, FIXTURE_MODEL_SHA256,
                    1, now=NOW, approved=True, halted=False)['fields'])
                self.assertNotIn('SYNTHETIC PRIVATE LABEL', _json(request))
                result = _supervise(request, halt_check=lambda: False, timeout_ms=12000)
                self.assertEqual(result['review']['history_pin'], original)
                raw = result['response']
                for first_pin, current_pin in ((original, None), (original, drift),
                                               (None, original), (None, None)):
                    with self.subTest(first_pin=first_pin, current_pin=current_pin):
                        with self.assertRaises(ValueError):
                            store.complete_current(ticket, request, snap, snap, raw,
                                now=NOW, approved=True, halted=False, worker_drained=True,
                                history_pin=first_pin, current_history_pin=current_pin)
                        state = store.status(PLAN, halted=False)
                        self.assertEqual(state['state'], 'RESERVED')
                        self.assertEqual(state['attempts_used'], 1)
                with self.assertRaises(ValueError):
                    store.complete(ticket, request, snap, raw, now=NOW,
                                   approved=True, halted=False, worker_drained=True)
                self.assertEqual(store.status(PLAN, halted=False)['state'], 'RESERVED')
                done = store.complete_current(ticket, request, snap, snap, raw,
                    now=NOW, approved=True, halted=False, worker_drained=True,
                    history_pin=original, current_history_pin=fresh)
                self.assertEqual(done['state'], 'REVIEWED')
                self.assertEqual(done['attempts_used'], 1)
                self.assertEqual(done['review']['history_pin'], original)
                self.assertEqual(done['review']['source_hold'], 'SOURCE_REVIEW_REQUIRED')
                self.assertIs(done['review']['execution_eligible'], False)
                self.assertEqual(done['attempts'][0]['review_sha256'], _digest(done['review']))

    def test_history_pin_cannot_move_to_another_current_scope(self):
        pin = project(snapshot(), [])
        with self.assertRaisesRegex(ValueError, 'scope'):
            build_request(snapshot(held=True), FIXTURE_MODEL_SHA256, 1,
                          now=NOW, approved=True, halted=False, history_pin=pin)
        with self.assertRaises(ValueError):
            build_request(snapshot(), FIXTURE_MODEL_SHA256, 4, now=NOW,
                          approved=True, halted=False, history_pin=pin)
        with self.assertRaises(PermissionError):
            build_request(snapshot(), FIXTURE_MODEL_SHA256, 1, now=NOW,
                          approved=True, halted=True, history_pin=pin)
