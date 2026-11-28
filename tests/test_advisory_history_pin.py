import unittest

from nexus_exchange.advisory_history_pin import validate_history_pin, match_history_pins


def pin():
    return dict(format='nexus-advisory-history-pin-v1', plan_id='a'*64,
                current_scope_sha256='b'*64, rfq_scope_sha256='c'*64,
                scope_history_sha256='d'*64, recall_sha256='e'*64,
                historical_only=True, current_status='NOT_REVALIDATED',
                independently_verified=False, external_authority=False,
                execution_eligible=False)


class AdvisoryHistoryPinTests(unittest.TestCase):
    def test_fixed_shape_and_detached_copy(self):
        original = pin()
        checked = validate_history_pin(original)
        self.assertEqual(checked, original)
        checked['plan_id'] = 'f'*64
        self.assertEqual(original, pin())

    def test_reject_malformed_or_authoritative_history(self):
        for changes in (dict(plan_id='0'*64), dict(scope_history_sha256='D'*64),
                        dict(recall_sha256=None), dict(historical_only=1),
                        dict(independently_verified=0), dict(external_authority=True),
                        dict(execution_eligible=True), dict(current_status='VERIFIED'),
                        dict(supplier='PRIVATE'), dict(format='v2')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_history_pin(dict(pin(), **changes))
        incomplete = pin()
        del incomplete['recall_sha256']
        with self.assertRaises(ValueError):
            validate_history_pin(incomplete)

    def test_fresh_membership_and_scope_must_match(self):
        self.assertEqual(match_history_pins(pin(), pin()), pin())
        for key in ('plan_id', 'current_scope_sha256', 'rfq_scope_sha256',
                    'scope_history_sha256', 'recall_sha256'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                match_history_pins(pin(), dict(pin(), **{key:'f'*64}))
        for first, second in ((pin(), None), (None, pin())):
            with self.assertRaises(ValueError):
                match_history_pins(first, second)
        self.assertIsNone(match_history_pins(None, None))
