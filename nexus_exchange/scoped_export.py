"""Exact local preview pins, not authorization to export or deliver."""
import re

_FIELDS = {'expected_contract', 'expected_report', 'expected_artifact'}


def checked_export_pins(pins):
    """Require all three canonical SHA-256 pins, without extra fields."""
    if (type(pins) is not dict or set(pins) != _FIELDS
            or any(type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value)
                   for value in pins.values())):
        raise ValueError('EXACT_PREVIEW_PINS_REQUIRED')
    return dict(pins)


def require_matching_pins(expected, actual):
    """Recomputed artifact, report and contract must all match the preview."""
    pinned = checked_export_pins(expected)
    if checked_export_pins(actual) != pinned:
        raise ValueError('SCOPED_PREVIEW_CHANGED')
    return pinned
