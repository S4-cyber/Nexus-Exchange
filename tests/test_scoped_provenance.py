import copy
from hashlib import sha256
import json
import unittest

from nexus_exchange.scoped_provenance import build_provenance, validate_provenance
from nexus_exchange.service_handoff import review_scope

FLAGS = ('requirements_verified','commercial_facts_verified','zero_capital_verified',
         'delivery_feasibility_verified','independently_verified','execution_eligible',
         'external_authority','dispatch_enabled','source_bytes_checked')
STAMP = '2026-11-25T00:01:00.000000+00:00'
CREATED = '2026-11-25T00:02:00.000000+00:00'


def seal(value, key):
    value.pop(key, None)
    value[key] = sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
    return value


def fixture():
    context = dict(version=1, source='sam', lead_key='a'*64, profile_revision='b'*64,
                   observation_sha256='c'*64, retrieved_at='2026-11-25T00:00:00.000000+00:00')
    spec = dict(input_sha256='d'*64, columns=['id','name'], key_column='id', expected_rows=2)
    declared = dict(input_format='UTF8_CSV',input_bytes=27,max_cell_chars=30,
        preserve_all_fields=True,requires_deduplication=False,requires_inference=False,
        requires_formulas=False,specification=copy.deepcopy(spec))
    assessment = seal(dict(format='nexus-declared-operator-requirements-v1',
        capability_id='csv_preserve_and_standardize_v2',catalog_sha256='e'*64,
        declared_input=declared,declared_structure_fits=True,reasons=[],
        **dict.fromkeys((*FLAGS,'capability_verified_for_lead'),False)), 'assessment_sha256')
    review = seal(dict(format='nexus-scoped-service-review-v1',context=copy.deepcopy(context),
        evaluated_at=STAMP,state='DECLARED_STRUCTURE_FITS',source_hold=None,
        source_blockers=['CASH_EXPOSURE_UNKNOWN','OWNER_APPROVAL_REQUIRED'],
        title_assessment_sha256='f'*64,title_hint_matches_declared_service=False,
        requirements_assessment=assessment,**dict.fromkeys(FLAGS,False)),'review_sha256')
    contract = dict(format='nexus-csv-deliverable-contract-v2',context=context,specification=spec)
    report = dict(input_bytes=27)
    return review,contract,report


class ScopedProvenanceTests(unittest.TestCase):
    def test_complete_review_retained_and_detached(self):
        review,contract,report=fixture()
        record=build_provenance(review,review_scope(review),contract,report)
        self.assertEqual(record['review'],review)
        self.assertEqual(validate_provenance(record,contract,report,CREATED),record)
        review['source_blockers'].append('ALTERED')
        self.assertNotEqual(record['review'],review)

    def test_modified_review_or_assessment_rejected_even_with_resealed_outer_hash(self):
        review,contract,report=fixture()
        record=build_provenance(review,review_scope(review),contract,report)
        record['review']['requirements_assessment']['declared_input']['max_cell_chars']=20
        seal(record['review'],'review_sha256')
        record['review_scope_sha256']=review_scope(record['review'])
        with self.assertRaises(ValueError):
            validate_provenance(record,contract,report,CREATED)

    def test_false_authority_and_exact_contract_binding(self):
        for change in (dict(external_authority=True),dict(source_hold='SOURCE_REVIEW_REQUIRED'),
                       dict(state='SOURCE_HELD'),dict(source_bytes_checked=0)):
            review,contract,report=fixture(); review.update(change); seal(review,'review_sha256')
            with self.subTest(change=change),self.assertRaises(ValueError):
                build_provenance(review,review_scope(review),contract,report)
        review,contract,report=fixture()
        for changed in (dict(contract,format='other'),dict(contract,context=dict(contract['context'],lead_key='0'*64)),
                        dict(contract,specification=dict(contract['specification'],expected_rows=3))):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                build_provenance(review,review_scope(review),changed,report)
        with self.assertRaises(ValueError):
            build_provenance(review,review_scope(review),contract,dict(input_bytes=28))

    def test_registration_time_and_unknown_fields(self):
        review,contract,report=fixture()
        record=build_provenance(review,review_scope(review),contract,report)
        for changed in (dict(record,other=True),dict(record,review_scope_sha256='0'*64)):
            with self.assertRaises(ValueError):
                validate_provenance(changed,contract,report,CREATED)
        with self.assertRaises(ValueError):
            validate_provenance(record,contract,report,'2026-11-25T00:00:30.000000+00:00')

    def test_reconciliation_second_input_bound(self):
        review,contract,report=fixture()
        assessment=review['requirements_assessment']; declared=assessment['declared_input']
        assessment['capability_id']='csv_key_reconciliation_v1'; declared['preserve_all_fields']=False
        declared['right_input_bytes']=25
        declared['specification'].update(right_input_sha256='1'*64,right_expected_rows=2)
        contract['specification']=copy.deepcopy(declared['specification'])
        contract['format']='nexus-csv-key-reconciliation-contract-v1'
        seal(assessment,'assessment_sha256'); seal(review,'review_sha256')
        report['right_input_bytes']=25
        record=build_provenance(review,review_scope(review),contract,report)
        self.assertEqual(validate_provenance(record,contract,report,CREATED),record)
        with self.assertRaises(ValueError):
            validate_provenance(record,contract,dict(report,right_input_bytes=24),CREATED)
