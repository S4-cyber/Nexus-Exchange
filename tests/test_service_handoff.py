import copy
from hashlib import sha256
import json
import unittest
from nexus_exchange.service_handoff import review_scope, checked_sample_inputs, checked_review_route

RAW = b'id,name\n1,Alpha\n'
RIGHT = b'id,name\n2,Beta\n'
CONTEXT = {'source': 'sam', 'lead_key': 'synthetic', 'profile_revision': 'a'*64,
           'retrieved_at': '2026-11-25T00:00:00Z', 'observation_sha256': 'b'*64}
REVIEW_FLAGS = ('requirements_verified', 'commercial_facts_verified', 'zero_capital_verified',
                'delivery_feasibility_verified', 'independently_verified', 'execution_eligible',
                'external_authority', 'dispatch_enabled', 'source_bytes_checked')


def seal(record, field):
    payload = {k:v for k,v in record.items() if k != field}
    record[field] = sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def fixture(capability='csv_preserve_and_standardize_v2', raw=RAW):
    reconcile = capability == 'csv_key_reconciliation_v1'
    spec = dict(input_sha256=sha256(raw).hexdigest(), columns=['id','name'],
                key_column='id', expected_rows=1)
    declared = dict(input_format='UTF8_JSON_RECORDS' if capability == 'json_string_records_to_csv_v1' else 'UTF8_CSV',
                    input_bytes=len(raw), max_cell_chars=10, specification=spec,
                    preserve_all_fields=capability not in ('csv_column_quality_profile_v1','csv_key_reconciliation_v1'),
                    requires_deduplication=False, requires_inference=False, requires_formulas=False)
    if reconcile:
        declared['right_input_bytes'] = len(RIGHT)
        spec.update(right_input_sha256=sha256(RIGHT).hexdigest(), right_expected_rows=1)
    assessment = dict(format='nexus-declared-operator-requirements-v1', capability_id=capability,
        catalog_sha256='d'*64, declared_input=declared, declared_structure_fits=True, reasons=[],
        capability_verified_for_lead=False, **dict.fromkeys(REVIEW_FLAGS,False))
    seal(assessment,'assessment_sha256')
    review = dict(format='nexus-scoped-service-review-v1', context=copy.deepcopy(CONTEXT),
        state='DECLARED_STRUCTURE_FITS', source_hold=None, source_blockers=['REQUIREMENTS_UNVERIFIED'],
        title_assessment_sha256='c'*64, evaluated_at='2026-11-25T00:01:00.000000+00:00',
        title_hint_matches_declared_service=True, requirements_assessment=assessment,
        **dict.fromkeys(REVIEW_FLAGS,False))
    seal(review,'review_sha256')
    return review


class ServiceHandoffTests(unittest.TestCase):
    def test_exact_scope_is_stable_across_reevaluation_time(self):
        review = fixture()
        changed = copy.deepcopy(review)
        changed['evaluated_at'] = '2026-11-25T00:02:00.000000+00:00'
        seal(changed,'review_sha256')
        self.assertEqual(review_scope(review), review_scope(changed))
        self.assertEqual(checked_review_route(changed,review_scope(review),CONTEXT),('UTF8_CSV','PRESERVE'))
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
            seal(review,'review_sha256')
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

    def test_resealed_top_level_claims_never_authorize_sample(self):
        for flag in REVIEW_FLAGS:
            for value in (True,0,None):
                review=fixture(); review[flag]=value; seal(review,'review_sha256')
                with self.subTest(flag=flag,value=value),self.assertRaises(ValueError):
                    checked_review_route(review,review_scope(review),CONTEXT)

    def test_resealed_assessment_claims_and_unresolved_reasons_rejected(self):
        changes=[(flag,value) for flag in (*REVIEW_FLAGS,'capability_verified_for_lead')
                 for value in (True,0,None)] + [('reasons',['UNRESOLVED'])]
        for key,value in changes:
            review=fixture(); assessment=review['requirements_assessment']; assessment[key]=value
            seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                checked_review_route(review,review_scope(review),CONTEXT)

    def test_invalid_digest_or_incomplete_schema_rejected_before_input(self):
        for case in ('review_digest','assessment_digest','missing_flag','extra_field','missing_nested_flag','extra_nested_field'):
            review=fixture(); assessment=review['requirements_assessment']
            if case=='review_digest':
                review['review_sha256']='e'*64
            elif case=='assessment_digest':
                assessment['assessment_sha256']='e'*64; seal(review,'review_sha256')
            elif case=='missing_flag':
                del review['requirements_verified']; seal(review,'review_sha256')
            elif case=='extra_field':
                review['extra']=True; seal(review,'review_sha256')
            elif case=='missing_nested_flag':
                del assessment['source_bytes_checked']; seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
            else:
                assessment['extra']=True; seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
            with self.subTest(case=case),self.assertRaises(ValueError):
                checked_review_route(review,review_scope(review),CONTEXT)

    def test_resealed_unsupported_declarations_rejected_before_input(self):
        changes=(('requires_inference',True),('requires_formulas',True),
                 ('requires_deduplication',True),('preserve_all_fields',False),
                 ('input_bytes',0),('input_bytes',True),('max_cell_chars',257))
        for key,value in changes:
            review=fixture(); assessment=review['requirements_assessment']
            assessment['declared_input'][key]=value
            seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                checked_review_route(review,review_scope(review),CONTEXT)
        review=fixture('csv_key_reconciliation_v1')
        assessment=review['requirements_assessment']; assessment['declared_input']['right_input_bytes']=None
        seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
        with self.assertRaises(ValueError):
            checked_review_route(review,review_scope(review),CONTEXT)
