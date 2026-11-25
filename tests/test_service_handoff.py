import copy
from hashlib import sha256
import unittest
from nexus_exchange.service_handoff import review_scope, checked_sample_inputs

RAW = b'id,name\n1,Alpha\n'
RIGHT = b'id,name\n2,Beta\n'
CONTEXT = {'source': 'sam', 'lead_key': 'synthetic', 'profile_revision': 'a'*64,
           'retrieved_at': '2026-11-25T00:00:00Z', 'observation_sha256': 'b'*64}


def fixture(capability='csv_preserve_and_standardize_v2', raw=RAW):
    reconcile = capability == 'csv_key_reconciliation_v1'
    spec = dict(input_sha256=sha256(raw).hexdigest(), columns=['id','name'],
                key_column='id', expected_rows=1)
    declared = dict(input_format='UTF8_JSON_RECORDS' if capability == 'json_string_records_to_csv_v1' else 'UTF8_CSV',
                    input_bytes=len(raw), max_cell_chars=10, specification=spec)
    if reconcile:
        declared['right_input_bytes'] = len(RIGHT)
        spec.update(right_input_sha256=sha256(RIGHT).hexdigest(), right_expected_rows=1)
    return dict(context=copy.deepcopy(CONTEXT), state='DECLARED_STRUCTURE_FITS', source_hold=None,
        source_blockers=[], title_assessment_sha256='c'*64, evaluated_at='2026-11-25T00:00:00Z',
        requirements_assessment=dict(capability_id=capability, declared_input=declared,
            declared_structure_fits=True, assessment_sha256='d'*64),
        external_authority=False, execution_eligible=False, dispatch_enabled=False)


class ServiceHandoffTests(unittest.TestCase):
    def test_exact_scope_is_stable_across_reevaluation_time(self):
        review = fixture()
        changed = copy.deepcopy(review)
        changed['evaluated_at'] = '2026-11-25T00:01:00Z'
        self.assertEqual(review_scope(review), review_scope(changed))
        changed['context']['lead_key'] = 'another'
        self.assertNotEqual(review_scope(review), review_scope(changed))

    def test_four_service_routes_and_copy(self):
        for capability, source, operation in (
                ('csv_preserve_and_standardize_v2','UTF8_CSV','PRESERVE'),
                ('json_string_records_to_csv_v1','UTF8_JSON_RECORDS','PRESERVE'),
                ('csv_column_quality_profile_v1','UTF8_CSV','COLUMN_PROFILE'),
                ('csv_key_reconciliation_v1','UTF8_CSV','RECONCILE')):
            with self.subTest(capability=capability):
                review = fixture(capability)
                inputs = checked_sample_inputs(review, review_scope(review), CONTEXT, RAW,
                    right_raw=RIGHT if operation=='RECONCILE' else None)
                self.assertEqual((inputs['source_format'],inputs['operation']),(source,operation))
                self.assertEqual(inputs['specification'],review['requirements_assessment']['declared_input']['specification'])
                inputs['specification']['columns'].append('other')
                self.assertEqual(len(review['requirements_assessment']['declared_input']['specification']['columns']),2)

    def test_same_size_changed_bytes_and_wrong_sizes_rejected(self):
        review=fixture()
        for raw in (RAW.replace(b'Alpha',b'Omega'),RAW+b' ',bytearray(RAW)):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                checked_sample_inputs(review,review_scope(review),CONTEXT,raw)

    def test_scope_and_source_holds_are_never_overridden(self):
        for change in ({'state':'SOURCE_HELD'}, {'source_hold':'SOURCE_REVIEW_REQUIRED'},
                       {'external_authority':True}, {'execution_eligible':0}, {'dispatch_enabled':True}):
            review=fixture(); review.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                checked_sample_inputs(review,review_scope(review),CONTEXT,RAW)
        review=fixture()
        with self.assertRaises(ValueError):
            checked_sample_inputs(review,'f'*64,CONTEXT,RAW)
        with self.assertRaises(ValueError):
            checked_sample_inputs(review,review_scope(review),dict(CONTEXT,lead_key='other'),RAW)

    def test_second_input_must_match_exact_review(self):
        review=fixture('csv_key_reconciliation_v1')
        for right in (None,RIGHT+b' ',RIGHT.replace(b'Beta',b'Zeta')):
            with self.subTest(right=right),self.assertRaises(ValueError):
                checked_sample_inputs(review,review_scope(review),CONTEXT,RAW,right_raw=right)
        single=fixture()
        with self.assertRaises(ValueError):
            checked_sample_inputs(single,review_scope(single),CONTEXT,RAW,right_raw=RIGHT)

    def test_review_changes_invalidate_scope(self):
        review=fixture(); pin=review_scope(review)
        for path,value in (('state','SOURCE_HELD'),('source_blockers',['OBSERVATION_STALE']),('title_assessment_sha256','f'*64)):
            changed=copy.deepcopy(review); changed[path]=value
            self.assertNotEqual(pin,review_scope(changed))
        changed=copy.deepcopy(review); changed['requirements_assessment']['assessment_sha256']='e'*64
        self.assertNotEqual(pin,review_scope(changed))
