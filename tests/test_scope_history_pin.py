import unittest
from nexus_exchange.quote_history_recall import build_recall

PLAN, SCOPE = 'a'*64, 'b'*64


def row(key, snapshot, stamp, scope=SCOPE):
    return dict(plan_id=PLAN, scope_sha256=scope, receipt_sha256=key*64,
                snapshot_sha256=snapshot*64, rechecked_at=stamp, historical_only=True,
                current_status='NOT_REVALIDATED', external_authority=False,
                execution_eligible=False)


class ScopeHistoryPinTests(unittest.TestCase):
    def test_hidden_receipt_replacement_changes_pin(self):
        old = row('1', 'c', '2026-01-01T00:00:00+00:00')
        newest = row('2', 'c', '2026-01-03T00:00:00+00:00')
        hidden = row('3', 'd', '2026-01-02T00:00:00+00:00')
        baseline = build_recall([old, newest, hidden], PLAN, SCOPE, limit=1)
        for changed in ([dict(old, receipt_sha256='4'*64), newest, hidden],
                        [old, newest, dict(hidden, receipt_sha256='5'*64)]):
            result = build_recall(changed, PLAN, SCOPE, limit=1)
            self.assertEqual(result['references'], baseline['references'])
            self.assertEqual(result['matching_receipts'], baseline['matching_receipts'])
            self.assertNotEqual(result['scope_history_sha256'], baseline['scope_history_sha256'])
            self.assertNotEqual(result['recall_sha256'], baseline['recall_sha256'])

    def test_pin_ignores_other_scope_order_and_result_budget(self):
        rows = [row('1', 'c', '2026-01-01T00:00:00+00:00'),
                row('2', 'd', '2026-01-02T00:00:00+00:00')]
        baseline = build_recall(rows, PLAN, SCOPE, limit=1)
        changed = build_recall(list(reversed(rows)) + [row('3', 'e', '2026-01-03T00:00:00+00:00', 'f'*64)],
                               PLAN, SCOPE, limit=16)
        self.assertEqual(baseline['scope_history_sha256'], changed['scope_history_sha256'])
        self.assertNotIn('1'*64, str(baseline['references']))
        self.assertNotEqual(baseline['scope_history_sha256'], build_recall([], PLAN, SCOPE)['scope_history_sha256'])
