import copy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nexus_exchange.council_history_context import build_council_history_context
from nexus_exchange.context_packet import build_packet
from nexus_exchange.local_advisory import _digest
from test_context_packet import NOW, PLAN, snapshot, rehash
from test_quote_history_reviewed import comparison, historical, SCOPE

STAMP = NOW.isoformat(timespec='microseconds')


class CouncilHistoryContextTests(unittest.TestCase):
    def inputs(self, **changes):
        row = historical()
        row['rechecked_at'] = STAMP
        args = dict(limit=1, confirmed=True,
                    inspect=Mock(side_effect=[snapshot(held=True), snapshot(held=True)]),
                    compare=Mock(return_value=comparison(STAMP)),
                    read_history=Mock(return_value=[row]), permit=Mock(), clock=lambda: NOW)
        args.update(changes)
        return args

    def test_reference_only_history_preserves_current_holds_and_evidence(self):
        args = self.inputs()
        result = build_council_history_context(PLAN, **args)
        self.assertEqual(result['council'], build_packet(snapshot(held=True), 'evidence', halted=False))
        self.assertEqual(result['history']['recall']['scope_sha256'], SCOPE)
        self.assertEqual(result['history']['recall']['matching_receipts'], 1)
        self.assertEqual(result['council']['data']['summary']['source_hold'], 'SOURCE_REVIEW_REQUIRED')
        self.assertTrue(all(not ids for ids in result['council']['data']['evidence'].values()))
        for key in ('history_used_for_scoring', 'external_authority', 'execution_eligible',
                    'current_decision', 'independently_verified', 'dispatch_enabled', 'release_eligible'):
            self.assertIs(result[key], False)
        self.assertEqual(result['context_sha256'], _digest({k:v for k,v in result.items() if k != 'context_sha256'}))
        self.assertNotIn('SYNTHETIC PRIVATE LABEL', str(result))
        self.assertEqual(args['inspect'].call_count, 2)
        self.assertEqual(args['compare'].call_count, 2)
        self.assertEqual(args['read_history'].call_count, 3)

    def test_consent_and_halt_deny_before_history_read(self):
        for changes, error in ((dict(confirmed=1), PermissionError), (dict(limit=True), ValueError),
                               (dict(limit=17), ValueError),
                               (dict(permit=Mock(side_effect=PermissionError('halt'))), PermissionError)):
            args = self.inputs(**changes)
            with self.subTest(changes=changes), self.assertRaises(error):
                build_council_history_context(PLAN, **args)
            args['inspect'].assert_not_called()
            args['read_history'].assert_not_called()
        args = self.inputs(permit=Mock(side_effect=[None, None, None, PermissionError('halt')]))
        with self.assertRaises(PermissionError):
            build_council_history_context(PLAN, **args)
        self.assertEqual(args['inspect'].call_count, 1)

    def test_changed_scope_or_future_history_is_rejected(self):
        args = self.inputs(inspect=Mock(side_effect=[snapshot(held=True), snapshot()]))
        with self.assertRaisesRegex(ValueError, 'scope'):
            build_council_history_context(PLAN, **args)
        future = historical()
        future['rechecked_at'] = (NOW + timedelta(seconds=1)).isoformat()
        args = self.inputs(read_history=Mock(return_value=[future]))
        with self.assertRaisesRegex(ValueError, 'postdates'):
            build_council_history_context(PLAN, **args)
        args = self.inputs(compare=Mock(return_value=comparison((NOW+timedelta(seconds=1)).isoformat(timespec='microseconds'))))
        with self.assertRaisesRegex(ValueError, 'inspection interval'):
            build_council_history_context(PLAN, **args)

    def test_clock_only_progress_and_detached_return(self):
        before = snapshot()
        later = copy.deepcopy(before)
        later['evaluated_at'] = (NOW+timedelta(microseconds=1)).isoformat(timespec='microseconds')
        later['modeled_collection_wait_us'] -= 1
        later['schedule_sha256'] = '1'*64
        rehash(later)
        args = self.inputs(inspect=Mock(side_effect=[before, later]), clock=lambda: NOW+timedelta(microseconds=1))
        result = build_council_history_context(PLAN, **args)
        self.assertEqual(result['council']['snapshot_sha256'], later['snapshot_sha256'])
        result['council']['scope']['source'] = 'changed'
        self.assertEqual(later['context']['source'], 'sam')

    def test_runtime_facade_does_not_reserve_attempt_or_create_history(self):
        from nexus_exchange.runtime_guard import RuntimeGuard
        from nexus_exchange.operator_scenarios import OperatorScenario
        from nexus_exchange.scenario_council import ScenarioCouncil
        from nexus_exchange.advisory_attempts import DB_NAME
        from nexus_exchange.quote_history_store import DB_NAME as HISTORY_DB
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with RuntimeGuard(root, clock=lambda: NOW) as guard:
                guard.resume()
                with patch.object(ScenarioCouncil, 'inspect', return_value=snapshot()) as inspect, \
                        patch.object(OperatorScenario, 'quote_compare', return_value=comparison(STAMP)) as compare:
                    with self.assertRaises(ValueError):
                        guard.quote_history_action('council_recall', PLAN, entries=[], limit=1,
                                                   confirmed=True, scope_sha256=SCOPE)
                    inspect.assert_not_called()
                    compare.assert_not_called()
                    result = guard.quote_history_action('council_recall', PLAN, entries=[], limit=1, confirmed=True)
                    self.assertEqual(result['history']['recall']['matching_receipts'], 0)
                    self.assertEqual(inspect.call_count, 2)
                    self.assertEqual(compare.call_count, 2)
                    self.assertFalse((root / DB_NAME).exists())
                    self.assertFalse((root / HISTORY_DB).exists())
                    self.assertFalse((root / 'council.sqlite3').exists())
                    guard.set()
                    with self.assertRaises(PermissionError):
                        guard.quote_history_action('council_recall', PLAN, entries=[], limit=1, confirmed=True)
                    self.assertEqual(inspect.call_count, 2)

    def test_memory_change_after_second_council_inspection_fails_closed(self):
        original = historical()
        original['rechecked_at'] = STAMP
        changed = dict(original, receipt_sha256='1'*64)
        read = Mock(side_effect=[[original], [original], [changed]])
        args = self.inputs(read_history=read)
        with self.assertRaisesRegex(ValueError, 'changed during Council review'):
            build_council_history_context(PLAN, **args)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(args['inspect'].call_count, 2)
