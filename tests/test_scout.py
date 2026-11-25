import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from nexus_exchange.scout import normalize, deduplicate


def fixture(**overrides):
    return dict(source='fixture', external_id='ABC-1', title='Monitor procurement',
                source_url='https://example.org/notices/ABC-1',
                retrieved_at='2026-11-24T15:00:00-08:00',
                deadline='2026-12-01T12:00:00-08:00', currency='usd',
                amount='1250.50') | overrides


class ScoutTests(unittest.TestCase):
    def test_normalization(self):
        item = normalize(fixture())
        self.assertEqual(item.currency, 'USD')
        self.assertEqual(item.amount, Decimal('1250.50'))
        self.assertEqual(item.retrieved_at.isoformat(), '2026-11-24T23:00:00+00:00')
        self.assertEqual(item.deadline.isoformat(), '2026-12-01T20:00:00+00:00')
        self.assertEqual(item.source_url, fixture()['source_url'])
        with self.assertRaises(FrozenInstanceError):
            item.title = 'changed'

    def test_identity(self):
        item = normalize(fixture())
        self.assertEqual(item.key, normalize(fixture(title='updated')).key)
        self.assertNotEqual(item.key, normalize(fixture(source='other')).key)

    def test_invalid(self):
        for overrides in [dict(source=''), dict(title=1), dict(extra=True),
                          dict(source_url='file:///tmp/a'), dict(source_url='https://u:p@example.org/x'),
                          dict(source_url='https://example.org:bad/x'), dict(retrieved_at='2026-11-24'),
                          dict(deadline='2026-12-01'), dict(currency='US'), dict(amount=True),
                          dict(amount='NaN'), dict(amount='-1'), dict(amount='1e100'),
                          dict(amount='1.00001'), dict(currency=None), dict(amount=None)]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                normalize(fixture(**overrides))
        for raw in [None, [], {}, {'source': 'x'}]:
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_unknown_optional_values(self):
        item = normalize(fixture(amount=None, currency=None, deadline=None))
        self.assertIsNone(item.amount)
        self.assertIsNone(item.deadline)

    def test_deduplication(self):
        a = normalize(fixture())
        b = normalize(fixture(title='Revised', retrieved_at='2026-11-25T00:00:00Z'))
        self.assertEqual(deduplicate([a,b,a]), (b,))
        self.assertEqual(deduplicate([b,a]), (b,))
        with self.assertRaises(ValueError):
            deduplicate([a, normalize(fixture(title='conflict'))])

    def test_deduplication_rejects_raw_records(self):
        with self.assertRaises(ValueError):
            deduplicate([fixture()])
