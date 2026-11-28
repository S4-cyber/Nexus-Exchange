import unittest

from nexus_exchange.quote_history_lineage import annotate_history


def observation(receipt, snapshot, *, plan='a', scope='b', time='2026-11-27T00:00:00+00:00'):
    return dict(receipt_sha256=receipt*64, snapshot_sha256=snapshot*64,
                plan_id=plan*64, scope_sha256=scope*64, rechecked_at=time,
                historical_only=True, current_status='NOT_REVALIDATED',
                execution_eligible=False, external_authority=False)


class HistoryLineageTests(unittest.TestCase):
    def test_deduplicate_and_distinguish_rechecks_from_distinct_snapshots(self):
        first = observation('1', 'c')
        repeat = observation('2', 'c', time='2026-11-27T00:00:01+00:00')
        changed = observation('3', 'd', time='2026-11-27T00:00:02+00:00')
        rows = annotate_history([first, changed, repeat, first])
        self.assertEqual([row['receipt_sha256'] for row in rows], ['3'*64, '2'*64, '1'*64])
        self.assertEqual([row['snapshot_observations'] for row in rows], [1, 2, 2])
        self.assertTrue(all(row['scope_snapshots'] == 2 for row in rows))
        self.assertTrue(all(row['supersession_status'] == 'NOT_ESTABLISHED' for row in rows))
        self.assertNotIn('scope_snapshots', first)

    def test_separate_scope_and_plan_and_no_authority(self):
        rows = annotate_history([observation('1', 'c'), observation('2', 'd', scope='e'),
                                 observation('3', 'd', plan='f')])
        self.assertTrue(all(row['scope_snapshots'] == 1 for row in rows))
        self.assertTrue(all(row['execution_eligible'] is False for row in rows))
        self.assertTrue(all(row['current_status'] == 'NOT_REVALIDATED' for row in rows))

    def test_reject_conflicts_and_bounded_input(self):
        first = observation('1', 'c')
        for rows in ([first, observation('1', 'd')], [first]*65, [dict(first, external_authority=True)]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                annotate_history(rows)
        self.assertEqual(annotate_history([]), [])
