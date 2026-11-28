import unittest
from unittest.mock import Mock

from nexus_exchange.operator_drafts import _digest, _json
from nexus_exchange.quote_comparison import _FLAGS
from nexus_exchange.quote_history_reviewed import review_scoped_recall

PLAN, SCOPE = 'a'*64, 'b'*64
STAMP = '2026-01-01T00:00:00.000000+00:00'
LATER = '2026-01-01T00:00:01.000000+00:00'


def comparison(stamp=STAMP, **changes):
    payload = dict(format='nexus-synthetic-quote-comparison-v1', mode='SIMULATION_ONLY',
                   plan_id=PLAN, scope_sha256=SCOPE, compared_at=stamp,
                   rows=[{'supplier': 'SYNTHETIC PRIVATE LABEL', 'total_cents': 123}],
                   **dict.fromkeys(_FLAGS, False))
    payload.update(changes)
    return dict(payload, comparison_sha256=_digest(_json(payload)))


def historical(scope=SCOPE):
    return dict(plan_id=PLAN, scope_sha256=scope, receipt_sha256='c'*64 if scope == SCOPE else 'd'*64,
                snapshot_sha256='e'*64, rechecked_at=STAMP, historical_only=True,
                current_status='NOT_REVALIDATED', external_authority=False, execution_eligible=False)


class ReviewedHistoryTests(unittest.TestCase):
    def test_current_comparison_selects_scope_without_leaking_terms(self):
        before, after = comparison(), comparison(LATER)
        compare = Mock(side_effect=[before, after])
        read = Mock(return_value=[historical(), historical('f'*64)])
        permit = Mock()
        result = review_scoped_recall(PLAN, limit=1, confirmed=True,
                                      compare=compare, read_history=read, permit=permit)
        self.assertEqual(compare.call_count, 2)
        read.assert_called_once_with()
        self.assertEqual(result['recall']['scope_sha256'], SCOPE)
        self.assertEqual(result['recall']['matching_receipts'], 1)
        self.assertEqual(result['reviewed_comparison_sha256'], before['comparison_sha256'])
        self.assertEqual(result['rechecked_comparison_sha256'], after['comparison_sha256'])
        self.assertEqual(result['rechecked_at'], LATER)
        for key in ('external_authority', 'execution_eligible', 'current_decision', 'independently_verified'):
            self.assertIs(result[key], False)
        self.assertNotIn('SYNTHETIC PRIVATE LABEL', _json(result))
        self.assertNotIn('total_cents', _json(result))
        self.assertEqual(result['context_sha256'], _digest(_json({k: v for k, v in result.items() if k != 'context_sha256'})))

    def test_denies_before_reads_and_rejects_changed_comparison(self):
        compare, read, permit = Mock(), Mock(), Mock()
        for confirmed, limit, plan, error in ((1, 1, PLAN, PermissionError),
                (True, True, PLAN, ValueError), (True, 17, PLAN, ValueError),
                (True, 1, PLAN[:8], ValueError)):
            with self.subTest(confirmed=confirmed, limit=limit, plan=plan), self.assertRaises(error):
                review_scoped_recall(plan, limit=limit, confirmed=confirmed,
                                     compare=compare, read_history=read, permit=permit)
        compare.assert_not_called()
        read.assert_not_called()
        for bad in (comparison(LATER, scope_sha256='f'*64), comparison(LATER, rows=[]),
                    comparison(LATER, external_authority=True), comparison('2025-12-31T00:00:00.000000+00:00')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                review_scoped_recall(PLAN, limit=1, confirmed=True,
                    compare=Mock(side_effect=[comparison(), bad]), read_history=Mock(return_value=[]), permit=permit)
        for bad in (comparison(plan_id='f'*64), comparison(scope_sha256='bad'), comparison(execution_eligible=True)):
            read = Mock()
            with self.assertRaises(ValueError):
                review_scoped_recall(PLAN, limit=1, confirmed=True,
                    compare=Mock(return_value=bad), read_history=read, permit=permit)
            read.assert_not_called()

    def test_halt_and_mutation_withhold_recall(self):
        compare = Mock(return_value=comparison())
        permit = Mock(side_effect=[None, None, PermissionError('halted')])
        with self.assertRaises(PermissionError):
            review_scoped_recall(PLAN, limit=1, confirmed=True,
                compare=compare, read_history=Mock(return_value=[]), permit=permit)
        compare.assert_called_once_with()
        shared = comparison()
        def read():
            shared.update(comparison(LATER, rows=[]))
            return []
        with self.assertRaises(ValueError):
            review_scoped_recall(PLAN, limit=1, confirmed=True,
                compare=lambda: shared, read_history=read, permit=lambda: None)
