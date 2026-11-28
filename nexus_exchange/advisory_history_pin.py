"""Reference-only history binding for a cooperating trusted advisory owner.

Hashes pin consistency, not authenticity. No raw quotations, credentials,
current evidence, permissions or scoring inputs are projected into the worker.
"""
import re

_FORMAT = 'nexus-advisory-history-pin-v1'
_IDENTITIES = ('plan_id', 'current_scope_sha256', 'rfq_scope_sha256',
               'scope_history_sha256', 'recall_sha256')
_FLAGS = ('independently_verified', 'external_authority', 'execution_eligible')
_FIELDS = {'format', 'historical_only', 'current_status', *_IDENTITIES, *_FLAGS}


def validate_history_pin(pin):
    if (type(pin) is not dict or set(pin) != _FIELDS
            or pin['format'] != _FORMAT or pin['historical_only'] is not True
            or pin['current_status'] != 'NOT_REVALIDATED'
            or any(pin[key] is not False for key in _FLAGS)):
        raise ValueError('invalid advisory history pin schema or authority')
    for key in _IDENTITIES:
        value = pin[key]
        if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value) or value == '0'*64:
            raise ValueError('invalid advisory history identity')
    return dict(pin)


def match_history_pins(original, current):
    """Require independent, matching full membership pins; never fall back."""
    if original is None and current is None:
        return None
    original = validate_history_pin(original)
    current = validate_history_pin(current)
    if original != current:
        raise ValueError('advisory historical scope or membership changed')
    return original


def pin_for_snapshot(pin, snapshot):
    from .advisory_current_scope import _stable, _stamp
    from .local_advisory import _digest
    checked = validate_history_pin(pin)
    if (checked['plan_id'] != snapshot['plan_id'] or
            checked['current_scope_sha256'] != _digest(_stable(snapshot, _stamp(snapshot['evaluated_at'])))):
        raise ValueError('advisory history outside current Council scope')
    return checked


def build_history_pin(context, snapshot, *, halted=None):
    """Project a freshly built trusted local Council history context.

    The caller must independently build the context from actual local RFQ and
    history reads; do not accept external context merely because it hashes.
    """
    from .context_packet import validate_packet
    from .local_advisory import _digest, _permit
    _permit(True, halted)
    if type(context) is not dict or context.get('format') != 'nexus-council-history-context-v1':
        raise ValueError('exact Council history context required')
    if any(context.get(key) is not False for key in (*_FLAGS, 'history_used_for_scoring',
            'current_decision', 'dispatch_enabled', 'release_eligible')):
        raise ValueError('invalid Council history authority')
    if context.get('context_sha256') != _digest({k:v for k,v in context.items() if k != 'context_sha256'}):
        raise ValueError('Council history context integrity mismatch')
    packet = validate_packet(context['council'], snapshot, halted=halted)
    history = context['history']
    recall = history['recall']
    if (packet['level'] != 'evidence' or context['plan_id'] != snapshot['plan_id']
            or recall['plan_id'] != snapshot['plan_id']
            or recall['historical_only'] is not True or recall['current_status'] != 'NOT_REVALIDATED'
            or any(recall.get(key) is not False for key in (*_FLAGS, 'current_decision'))
            or recall['recall_sha256'] != _digest({k:v for k,v in recall.items() if k != 'recall_sha256'})):
        raise ValueError('invalid Council historical recall')
    return pin_for_snapshot(dict(format=_FORMAT, plan_id=context['plan_id'],
        current_scope_sha256=context['current_scope_sha256'], rfq_scope_sha256=recall['scope_sha256'],
        scope_history_sha256=recall['scope_history_sha256'], recall_sha256=recall['recall_sha256'],
        historical_only=True, current_status='NOT_REVALIDATED', **dict.fromkeys(_FLAGS, False)), snapshot)
