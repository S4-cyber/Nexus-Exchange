"""Local review-to-sample scope pins, not authentication or action authority."""
from copy import deepcopy
from hashlib import sha256
import json

_REVIEW_FLAGS = ('requirements_verified', 'commercial_facts_verified', 'zero_capital_verified',
                 'delivery_feasibility_verified', 'independently_verified', 'execution_eligible',
                 'external_authority', 'dispatch_enabled', 'source_bytes_checked')
_ASSESSMENT_FLAGS = (*_REVIEW_FLAGS, 'capability_verified_for_lead')
_REVIEW_FIELDS = {'format', 'context', 'evaluated_at', 'state', 'source_hold', 'source_blockers',
                  'title_assessment_sha256', 'title_hint_matches_declared_service',
                  'requirements_assessment', 'review_sha256', *_REVIEW_FLAGS}
_ASSESSMENT_FIELDS = {'format', 'capability_id', 'catalog_sha256', 'declared_input',
                      'declared_structure_fits', 'reasons', 'assessment_sha256', *_ASSESSMENT_FLAGS}
_DECLARED_FIELDS = {'input_format', 'input_bytes', 'max_cell_chars', 'preserve_all_fields',
                    'requires_deduplication', 'requires_inference', 'requires_formulas', 'specification'}

_ROUTES = {
    'csv_preserve_and_standardize_v2': ('UTF8_CSV', 'PRESERVE'),
    'json_string_records_to_csv_v1': ('UTF8_JSON_RECORDS', 'PRESERVE'),
    'csv_column_quality_profile_v1': ('UTF8_CSV', 'COLUMN_PROFILE'),
    'csv_key_reconciliation_v1': ('UTF8_CSV', 'RECONCILE'),
}
_SCOPE_FIELDS = ('context', 'state', 'source_hold', 'source_blockers',
                 'title_assessment_sha256', 'requirements_assessment',
                 'external_authority', 'execution_eligible', 'dispatch_enabled')


def review_scope(review):
    """Stable pin from a backend-generated review; UTC time is not authority.

    The runtime must derive a fresh review, not accept a caller-supplied one.
    """
    payload = {'format': 'nexus-local-service-handoff-v1',
               **{key: review[key] for key in _SCOPE_FIELDS}}
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('ascii')
    return sha256(encoded).hexdigest()


def _check_record(record, fields, flags, digest_field, expected_format):
    """Verify the complete backend projection without granting authenticity."""
    if (type(record) is not dict or set(record) != fields
            or record['format'] != expected_format
            or any(record[key] is not False for key in flags)):
        raise ValueError('INVALID_SCOPED_SERVICE_REVIEW')
    try:
        encoded = json.dumps({k:v for k,v in record.items() if k != digest_field},
                             sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, RecursionError):
        raise ValueError('INVALID_SCOPED_SERVICE_REVIEW') from None
    if type(record[digest_field]) is not str or record[digest_field] != sha256(encoded).hexdigest():
        raise ValueError('SCOPED_SERVICE_REVIEW_DIGEST_MISMATCH')


def checked_review_route(review, expected_scope, plan_context):
    """Validate fresh local review scope before reading any selected sample file.

    Keep historical v1 scope pins unchanged; validate the full current envelope
    separately, including claims not covered by that stable projection.
    """
    _check_record(review, _REVIEW_FIELDS, _REVIEW_FLAGS, 'review_sha256',
                  'nexus-scoped-service-review-v1')
    if (review['state'] != 'DECLARED_STRUCTURE_FITS' or review['source_hold'] is not None
            or type(review['title_hint_matches_declared_service']) is not bool
            or type(review['context']) is not dict or review['context'] != plan_context
            or type(expected_scope) is not str or review_scope(review) != expected_scope):
        raise ValueError('CURRENT_SCOPED_SERVICE_REVIEW_REQUIRED')
    assessment = review['requirements_assessment']
    _check_record(assessment, _ASSESSMENT_FIELDS, _ASSESSMENT_FLAGS, 'assessment_sha256',
                  'nexus-declared-operator-requirements-v1')
    capability = assessment['capability_id']
    if (assessment['declared_structure_fits'] is not True or assessment['reasons'] != []
            or type(capability) is not str or capability not in _ROUTES):
        raise ValueError('DECLARED_SERVICE_STRUCTURE_REQUIRED')
    source, operation = _ROUTES[capability]
    declared = assessment['declared_input']
    reconcile = operation == 'RECONCILE'
    if (type(declared) is not dict or set(declared) !=
            (_DECLARED_FIELDS | ({'right_input_bytes'} if reconcile else set()))
            or declared['input_format'] != source or type(declared['specification']) is not dict
            or declared['preserve_all_fields'] is not (operation == 'PRESERVE')
            or any(declared[key] is not False for key in
                   ('requires_deduplication', 'requires_inference', 'requires_formulas'))
            or type(declared['max_cell_chars']) is not int
            or not 0 <= declared['max_cell_chars'] <= 256):
        raise ValueError('DECLARED_SERVICE_STRUCTURE_REQUIRED')
    for key in ('input_bytes', 'right_input_bytes') if reconcile else ('input_bytes',):
        if type(declared[key]) is not int or not 1 <= declared[key] <= 256*1024:
            raise ValueError('DECLARED_SERVICE_STRUCTURE_REQUIRED')
    return source, operation


def checked_sample_inputs(review, expected_scope, plan_context, raw, *, right_raw=None):
    """Project exact current declared inputs after matching actual local bytes."""
    source, operation = checked_review_route(review, expected_scope, plan_context)
    declared = review['requirements_assessment']['declared_input']
    spec = declared['specification']

    def check(data, size, digest):
        if (type(data) is not bytes or type(size) is not int or not 1 <= size <= 256*1024
                or len(data) != size or sha256(data).hexdigest() != digest):
            raise ValueError('DECLARED_INPUT_BYTES_MISMATCH')

    check(raw, declared['input_bytes'], spec['input_sha256'])
    if operation == 'RECONCILE':
        check(right_raw, declared['right_input_bytes'], spec['right_input_sha256'])
    elif right_raw is not None:
        raise ValueError('UNEXPECTED_SECOND_INPUT')
    bound = declared['max_cell_chars']
    if type(bound) is not int or not 0 <= bound <= 256:
        raise ValueError('DECLARED_CELL_BOUND_REQUIRED')
    return dict(specification=deepcopy(spec), source_format=source,
                operation=operation, max_cell_chars=bound)
