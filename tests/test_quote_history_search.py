import unittest

from nexus_exchange.quote_history_search import filter_history, normalize_history_query


class QuoteHistorySearchTests(unittest.TestCase):
    def test_exact_prefix_preserves_lineage_order_and_detaches(self):
        rows = [dict(receipt_sha256='a'*64, scope_sha256='b'*64,
                     snapshot_sha256='c'*64, snapshot_observations=2),
                dict(receipt_sha256='d'*64, scope_sha256='b'*64,
                     snapshot_sha256='c'*64, snapshot_observations=2),
                dict(receipt_sha256='e'*64, scope_sha256='f'*64,
                     snapshot_sha256='1'*64, snapshot_observations=1)]
        self.assertEqual(filter_history(rows, ' BBBBBBBB '), rows[:2])
        self.assertEqual(filter_history(rows, 'c'*64), rows[:2])
        selected = filter_history(rows, 'a'*8)
        self.assertEqual(selected, rows[:1])
        selected[0]['snapshot_observations'] = 1
        self.assertEqual(rows[0]['snapshot_observations'], 2)
        self.assertEqual(filter_history(rows, ''), rows)
        self.assertEqual(filter_history(rows, '0'*8), [])

    def test_invalid_queries_and_batch_bounds(self):
        for query in (None, 1, True, 'a'*7, 'a'*65, 'g'*8, 'a'*8+'\n', ' '*257):
            with self.subTest(query=query), self.assertRaises(ValueError):
                normalize_history_query(query)
        for rows in (None, (), [{}]*65):
            with self.assertRaises(ValueError):
                filter_history(rows, '')
