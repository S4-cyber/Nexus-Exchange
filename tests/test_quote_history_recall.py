import unittest
from nexus_exchange.quote_history_recall import build_recall


PLAN, SCOPE = 'a'*64, 'b'*64


def row(key, snapshot, stamp, **changes):
    return dict(dict(plan_id=PLAN, scope_sha256=SCOPE, receipt_sha256=key*64,
                     snapshot_sha256=snapshot*64, rechecked_at=stamp,
                     historical_only=True, current_status='NOT_REVALIDATED',
                     external_authority=False, execution_eligible=False), **changes)


class QuoteHistoryRecallTests(unittest.TestCase):
    def test_scope_grouping_budget_and_detachment(self):
        rows = [row('1', 'c', '2026-01-01T00:00:00+00:00'),
                row('2', 'c', '2026-01-02T00:00:00+00:00'),
                row('3', 'd', '2026-01-01T00:00:00+00:00'),
                row('4', 'e', '2026-01-03T00:00:00+00:00', scope_sha256='f'*64)]
        packet = build_recall(rows, PLAN, SCOPE, limit=1)
        self.assertEqual(packet['matching_receipts'], 3)
        self.assertEqual(packet['distinct_snapshots'], 2)
        self.assertTrue(packet['truncated'])
        self.assertEqual(packet['references'], [dict(receipt_sha256='2'*64,
            snapshot_sha256='c'*64, rechecked_at='2026-01-02T00:00:00+00:00', observations=2)])
        self.assertEqual(packet, build_recall(list(reversed(rows)), PLAN, SCOPE, limit=1))
        self.assertFalse(packet['external_authority'])
        self.assertFalse(packet['execution_eligible'])
        self.assertFalse(packet['current_decision'])
        self.assertFalse(packet['independently_verified'])
        self.assertEqual(build_recall(rows, PLAN, '0'*64)['references'], [])
        packet['references'][0]['observations'] = 99
        self.assertEqual(build_recall(rows, PLAN, SCOPE, limit=1)['references'][0]['observations'], 2)

    def test_fail_closed_on_scope_authority_and_invalid_inputs(self):
        base = row('1', 'c', '2026-01-01T00:00:00+00:00')
        for changes in (dict(plan_id='f'*64), dict(external_authority=0),
                        dict(execution_eligible=True), dict(historical_only=1),
                        dict(current_status='VERIFIED'), dict(receipt_sha256='a'),
                        dict(rechecked_at='not a time')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_recall([dict(base, **changes)], PLAN, SCOPE)
        for rows in ([base, base], [base]*65, None):
            with self.assertRaises(ValueError):
                build_recall(rows, PLAN, SCOPE)
        for limit in (True, 0, 17):
            with self.assertRaises(ValueError):
                build_recall([], PLAN, SCOPE, limit=limit)
        with self.assertRaises(ValueError):
            build_recall([], PLAN, SCOPE[:8])
