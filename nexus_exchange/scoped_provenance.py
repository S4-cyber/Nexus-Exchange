"""Historical Scout review provenance for one immutable local obligation.

These checks establish local consistency only, not independent authenticity.
Historical validation does not consult a changing capability catalogue.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from .service_handoff import review_scope

FORMAT = 'nexus-scout-obligation-provenance-v1'
_FLAGS = ('requirements_verified','commercial_facts_verified','zero_capital_verified',
          'delivery_feasibility_verified','independently_verified','execution_eligible',
          'external_authority','dispatch_enabled','source_bytes_checked')
_REVIEW = {'format','context','evaluated_at','state','source_hold','source_blockers',
           'title_assessment_sha256','title_hint_matches_declared_service',
           'requirements_assessment','review_sha256',*_FLAGS}
_ASSESSMENT = {'format','capability_id','catalog_sha256','declared_input',
               'declared_structure_fits','reasons','assessment_sha256',
               'capability_verified_for_lead',*_FLAGS}
_DECLARED = {'input_format','input_bytes','max_cell_chars','preserve_all_fields',
             'requires_deduplication','requires_inference','requires_formulas','specification'}
_ROUTES = {
    'csv_preserve_and_standardize_v2': ('UTF8_CSV','nexus-csv-deliverable-contract-v2',True),
    'json_string_records_to_csv_v1': ('UTF8_JSON_RECORDS','nexus-json-records-to-csv-contract-v1',True),
    'csv_column_quality_profile_v1': ('UTF8_CSV','nexus-csv-column-profile-contract-v1',False),
    'csv_key_reconciliation_v1': ('UTF8_CSV','nexus-csv-key-reconciliation-contract-v1',False),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError('INVALID_SCOUT_PROVENANCE_SCHEMA')


def _hash(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('INVALID_SCOUT_PROVENANCE_DIGEST')
    return value


def _sealed(value, field):
    expected = sha256(_canonical({k:v for k,v in value.items() if k != field}).encode('ascii')).hexdigest()
    if _hash(value[field]) != expected:
        raise ValueError('SCOUT_PROVENANCE_DIGEST_MISMATCH')


def _stamp(value):
    if type(value) is not str or len(value) != 32:
        raise ValueError('INVALID_SCOUT_PROVENANCE_TIME')
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.astimezone(timezone.utc).isoformat(timespec='microseconds') != value:
        raise ValueError('INVALID_SCOUT_PROVENANCE_TIME')
    return dt


def build_provenance(review, expected_scope, contract, report):
    """Bind the freshly derived review to a previously validated sample."""
    _shape(review, _REVIEW)
    if (review['format'] != 'nexus-scoped-service-review-v1'
            or review['state'] != 'DECLARED_STRUCTURE_FITS' or review['source_hold'] is not None
            or any(review[k] is not False for k in _FLAGS)
            or _canonical(review['context']) != _canonical(contract['context'])
            or type(review['title_hint_matches_declared_service']) is not bool):
        raise ValueError('SCOUT_PROVENANCE_SCOPE_MISMATCH')
    blockers = review['source_blockers']
    if (type(blockers) is not list or not 1 <= len(blockers) <= 64
            or any(type(v) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}',v) for v in blockers)):
        raise ValueError('INVALID_SCOUT_PROVENANCE_BLOCKERS')
    _hash(review['title_assessment_sha256'])
    if _stamp(review['evaluated_at']) < _stamp(contract['context']['retrieved_at']):
        raise ValueError('SCOUT_PROVENANCE_PREDATES_SOURCE')
    assessment = review['requirements_assessment']
    _shape(assessment, _ASSESSMENT)
    capability = assessment['capability_id']
    if (assessment['format'] != 'nexus-declared-operator-requirements-v1'
            or type(capability) is not str or capability not in _ROUTES
            or assessment['declared_structure_fits'] is not True or assessment['reasons'] != []
            or any(assessment[k] is not False for k in (*_FLAGS,'capability_verified_for_lead'))):
        raise ValueError('INVALID_SCOUT_PROVENANCE_ASSESSMENT')
    _hash(assessment['catalog_sha256'])
    source, contract_format, preserve = _ROUTES[capability]
    reconcile = capability == 'csv_key_reconciliation_v1'
    declared = assessment['declared_input']
    _shape(declared, _DECLARED | ({'right_input_bytes'} if reconcile else set()))
    if (contract['format'] != contract_format or declared['input_format'] != source
            or declared['preserve_all_fields'] is not preserve
            or any(declared[k] is not False for k in ('requires_deduplication','requires_inference','requires_formulas'))
            or _canonical(declared['specification']) != _canonical(contract['specification'])
            or type(declared['max_cell_chars']) is not int or not 0 <= declared['max_cell_chars'] <= 256):
        raise ValueError('SCOUT_PROVENANCE_DECLARATION_MISMATCH')
    for key in ('input_bytes','right_input_bytes') if reconcile else ('input_bytes',):
        if type(declared[key]) is not int or not 1 <= declared[key] <= 256*1024 or declared[key] != report.get(key):
            raise ValueError('SCOUT_PROVENANCE_BYTE_COUNT_MISMATCH')
    _sealed(assessment,'assessment_sha256')
    _sealed(review,'review_sha256')
    if review_scope(review) != _hash(expected_scope):
        raise ValueError('SCOUT_PROVENANCE_REVIEW_MISMATCH')
    return dict(format=FORMAT,review_scope_sha256=expected_scope,review=deepcopy(review))


def validate_provenance(raw, contract, report, created_at):
    """Validate stored review material against historical registration time."""
    _shape(raw, {'format','review_scope_sha256','review'})
    canonical = build_provenance(raw['review'],raw['review_scope_sha256'],contract,report)
    if raw['format'] != FORMAT or _stamp(raw['review']['evaluated_at']) > _stamp(created_at):
        raise ValueError('SCOUT_PROVENANCE_REGISTRATION_MISMATCH')
    return canonical
