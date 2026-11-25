import copy
import unittest
from nexus_exchange.service_handoff import checked_review_route, review_scope
from test_service_handoff import fixture, CONTEXT


class ReviewRouteTests(unittest.TestCase):
    def test_four_routes_before_file_io(self):
        for capability, route in (
                ('csv_preserve_and_standardize_v2', ('UTF8_CSV', 'PRESERVE')),
                ('json_string_records_to_csv_v1', ('UTF8_JSON_RECORDS', 'PRESERVE')),
                ('csv_column_quality_profile_v1', ('UTF8_CSV', 'COLUMN_PROFILE')),
                ('csv_key_reconciliation_v1', ('UTF8_CSV', 'RECONCILE'))):
            with self.subTest(capability=capability):
                review = fixture(capability)
                self.assertEqual(checked_review_route(review, review_scope(review), CONTEXT), route)

    def test_rejects_held_forged_or_wrong_scope(self):
        for change in ({'source_hold':'SOURCE_REVIEW_REQUIRED'}, {'state':'SOURCE_HELD'},
                       {'external_authority':True}, {'execution_eligible':0}, {'dispatch_enabled':True}):
            review = fixture(); review.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                checked_review_route(review, review_scope(review), CONTEXT)
        review = fixture()
        with self.assertRaises(ValueError):
            checked_review_route(review, 'f'*64, CONTEXT)
        with self.assertRaises(ValueError):
            checked_review_route(review, review_scope(review), dict(CONTEXT, lead_key='other'))

    def test_requires_compatible_declared_specification(self):
        for change in ({'input_format':'OTHER'}, {'specification':None}):
            review=fixture(); review['requirements_assessment']['declared_input'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                checked_review_route(review, review_scope(review), CONTEXT)
        review=fixture(); review['requirements_assessment']['declared_structure_fits']=False
        with self.assertRaises(ValueError):
            checked_review_route(review, review_scope(review), CONTEXT)
