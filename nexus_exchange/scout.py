"""Offline opportunity normalization. Source assertions are not verification."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlsplit

_FIELDS = frozenset('source external_id title source_url retrieved_at deadline currency amount'.split())


def _text(value, limit):
    if type(value) is not str or not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid text')
    return value.strip()


def _timestamp(value):
    value = _text(value, 64)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('timestamp requires explicit offset')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError('invalid timestamp') from exc


def _url(value):
    value = _text(value, 2048)
    if any(c.isspace() for c in value) or '\\' in value:
        raise ValueError('invalid source URL')
    try:
        parts = urlsplit(value)
        port = parts.port
        if parts.scheme != 'https' or not parts.hostname or parts.username is not None or parts.password is not None or port not in (None, 443):
            raise ValueError('invalid source URL')
    except ValueError as exc:
        raise ValueError('invalid source URL') from exc
    return value


@dataclass(frozen=True, slots=True)
class Opportunity:
    key: str
    source: str
    external_id: str
    title: str
    source_url: str
    retrieved_at: datetime
    deadline: datetime | None
    currency: str | None
    amount: Decimal | None


def normalize(raw):
    if type(raw) is not dict or any(type(k) is not str for k in raw) or set(raw) != _FIELDS:
        raise ValueError('invalid opportunity schema')
    source = _text(raw['source'], 100)
    external_id = _text(raw['external_id'], 256)
    title = _text(raw['title'], 512)
    url = _url(raw['source_url'])
    retrieved = _timestamp(raw['retrieved_at'])
    deadline = None if raw['deadline'] is None else _timestamp(raw['deadline'])
    currency, amount = raw['currency'], raw['amount']
    if (currency is None) != (amount is None):
        raise ValueError('amount and currency must be paired')
    if currency is not None:
        if type(currency) is not str or not re.fullmatch('[A-Za-z]{3}', currency):
            raise ValueError('invalid currency code format')
        currency = currency.upper()
        if type(amount) is not str or not re.fullmatch(r'\d{1,12}(?:\.\d{1,4})?', amount):
            raise ValueError('invalid decimal amount')
        try:
            amount = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError('invalid decimal amount') from exc
    key = hashlib.sha256(json.dumps([source, external_id], ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return Opportunity(key, source, external_id, title, url, retrieved, deadline, currency, amount)


def deduplicate(records):
    """Latest observation wins; conflicting equal-time snapshots fail closed."""
    latest = {}
    seen = {}
    for item in records:
        if type(item) is not Opportunity:
            raise ValueError('expected normalized opportunity')
        snapshot = (item.key, item.retrieved_at)
        if snapshot in seen and seen[snapshot] != item:
            raise ValueError('conflicting snapshots')
        seen[snapshot] = item
        if item.key not in latest or item.retrieved_at > latest[item.key].retrieved_at:
            latest[item.key] = item
    return tuple(latest[key] for key in sorted(latest))
