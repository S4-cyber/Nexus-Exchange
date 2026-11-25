"""Local review-to-sample scope pins, not authentication or action authority."""
from copy import deepcopy
from hashlib import sha256
import json

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


def checked_sample_inputs(review, expected_scope, plan_context, raw, *, right_raw=None):
    """Project exact current declared inputs after matching actual local bytes."""
    if (review['state'] != 'DECLARED_STRUCTURE_FITS' or review['source_hold'] is not None
            or any(review[key] is not False for key in
                   ('external_authority', 'execution_eligible', 'dispatch_enabled'))
            or review['context'] != plan_context or type(expected_scope) is not str
            or review_scope(review) != expected_scope):
        raise ValueError('CURRENT_SCOPED_SERVICE_REVIEW_REQUIRED')
    assessment = review['requirements_assessment']
    if assessment['declared_structure_fits'] is not True or assessment['capability_id'] not in _ROUTES:
        raise ValueError('DECLARED_SERVICE_STRUCTURE_REQUIRED')
    source, operation = _ROUTES[assessment['capability_id']]
    declared = assessment['declared_input']
    spec = declared['specification']
    if declared['input_format'] != source or type(spec) is not dict:
        raise ValueError('DECLARED_SERVICE_STRUCTURE_REQUIRED')

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
