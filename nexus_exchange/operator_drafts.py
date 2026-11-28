"""Bounded, local-only supplier quotation request drafts.

Declared scenario and organization identifiers are not independently verified.
Acknowledgment is historical local review, never permission to contact a party.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import sqlite3
from pathlib import Path
import unicodedata

from .governor import Action, decide

MAX_DRAFTS = 10000
MAX_ITEMS = 16
MAX_PAYLOAD = 65536
_FLAGS = ('external_authority', 'send_enabled', 'recipient_verified',
          'reviewer_authenticated', 'current_decision')
_REQUEST = {'plan_id', 'observation_sha256', 'profile_revision', 'supplier', 'region', 'currency', 'items'}
_RECORD = {'version', 'draft', 'created_at', 'acknowledged_at'}


def _permit(halted):
    decision = decide(Action.DRAFT, halted=halted)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _digest(encoded):
    return hashlib.sha256(encoded.encode('ascii')).hexdigest()


def _match(value, pattern):
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise ValueError('invalid bounded identifier or quantity')
    return value


def _hash(value):
    return _match(value, '[0-9a-f]{64}')


def _text(value, maximum):
    if (type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip()
            or any(not c.isprintable() or unicodedata.category(c).startswith('C') for c in value)):
        raise ValueError('invalid single-line draft data')
    return value


def _shape(raw, fields):
    if type(raw) is not dict or any(type(k) is not str for k in raw) or set(raw) != fields:
        raise ValueError('invalid exact draft schema')


def _scheme(value):
    return _match(value, '[A-Z0-9][A-Z0-9_-]{0,63}')


def _normalize(raw):
    pinned = type(raw) is dict and 'supplier_profile_sha256' in raw
    _shape(raw, _REQUEST | {'supplier_profile_sha256'} if pinned else _REQUEST)
    supplier = raw['supplier']
    _shape(supplier, {'scheme', 'identifier'})
    party = dict(scheme=_scheme(supplier['scheme']), identifier=_text(supplier['identifier'], 128))
    if type(raw['currency']) is not str or raw['currency'] != 'USD':
        raise ValueError('USD-only draft scope')
    items = raw['items']
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError('bounded nonempty item list required')
    normalized = []
    for item in items:
        _shape(item, {'description', 'quantity', 'unit', 'classification'})
        classification = item['classification']
        _shape(classification, {'scheme', 'code'})
        quantity = Decimal(_match(item['quantity'], r'[0-9]{1,9}(?:\.[0-9]{1,4})?'))
        if quantity <= 0:
            raise ValueError('positive quantity required')
        canonical = format(quantity, 'f')
        if '.' in canonical:
            canonical = canonical.rstrip('0').rstrip('.')
        normalized.append(dict(description=_text(item['description'], 256), quantity=canonical,
            unit=_match(item['unit'], '[A-Za-z][A-Za-z0-9_-]{0,31}'),
            classification=dict(scheme=_scheme(classification['scheme']), code=_text(classification['code'], 128))))
    result = dict(plan_id=_hash(raw['plan_id']), observation_sha256=_hash(raw['observation_sha256']),
        profile_revision=_hash(raw['profile_revision']), supplier=party,
        region=_match(raw['region'], '[A-Z]{2}(?:-[A-Z0-9]{1,12})?'), currency='USD', items=normalized)
    if pinned:
        result['supplier_profile_sha256'] = _hash(raw['supplier_profile_sha256'])
    return result


def prepare_rfq(raw, *, halted=None):
    """Construct a deterministic nonbinding draft, without recipient address or price assertion."""
    _permit(halted)
    request = _normalize(raw)
    payload = dict(format='nexus-operator-rfq-v2' if 'supplier_profile_sha256' in request else
                   'nexus-operator-rfq-v1', request=request)
    return dict(payload, draft_id=_digest(_json(payload)), **dict.fromkeys(_FLAGS, False))


def _validated(draft):
    _shape(draft, {'format', 'request', 'draft_id', *_FLAGS})
    expected = prepare_rfq(draft['request'], halted=False)
    if any(draft[k] is not False for k in _FLAGS) or draft != expected:
        raise ValueError('draft identity or authority mismatch')
    return expected


def render_rfq(draft, *, halted=None):
    _permit(halted)
    request = _validated(draft)['request']
    lines = ['DRAFT ONLY — Request for quotation (non-binding)',
             'Recipient not verified; do not send without separate review.', '',
             'Could you provide a non-binding quotation for the following requirements?',
             'Delivery region: ' + request['region'], 'Requested currency: USD']
    for i, item in enumerate(request['items'], 1):
        lines.append(f"{i}. {_json(item['description'])} | quantity {item['quantity']} {item['unit']} | "
                     f"classification {item['classification']['scheme']}:{_json(item['classification']['code'])}")
    lines.extend(['', 'Please specify unit price, total price, fees and taxes, availability, lead time,',
                  'delivery terms, payment terms and quote validity.',
                  'This is an inquiry only, not an order, offer acceptance, or commitment.'])
    return '\n'.join(lines)


def _stamp(now):
    if type(now) is not datetime or now.utcoffset() is None:
        raise ValueError('aware draft clock required')
    return now.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _stored_stamp(value):
    if type(value) is not str or len(value) > 40:
        raise ValueError('invalid stored timestamp')
    if _stamp(datetime.fromisoformat(value)) != value:
        raise ValueError('noncanonical stored timestamp')
    return value


def _decode(key, payload, digest):
    if type(payload) is not str or len(payload) > MAX_PAYLOAD or _digest(payload) != digest:
        raise ValueError('draft storage integrity mismatch')
    record = json.loads(payload)
    _shape(record, _RECORD)
    if type(record['version']) is not int or record['version'] != 1:
        raise ValueError('invalid draft storage version')
    draft = _validated(record['draft'])
    if draft['draft_id'] != key or _json(record) != payload:
        raise ValueError('stored draft identity mismatch')
    created = _stored_stamp(record['created_at'])
    reviewed = record['acknowledged_at']
    if reviewed is not None and _stored_stamp(reviewed) < created:
        raise ValueError('draft acknowledgment predates creation')
    return record


def _view(record):
    return dict(record, state='DRAFT_ONLY' if record['acknowledged_at'] is None else
                'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY', historical_only=True, **dict.fromkeys(_FLAGS, False))


class DraftStore:
    """Trusted local storage; one immutable content identity and optional local acknowledgment."""
    def __init__(self, path, *, existing_only=False):
        if type(existing_only) is not bool:
            raise ValueError('invalid draft storage mode')
        if existing_only:
            path = Path(path)
            if path.is_symlink() or not path.is_file():
                raise ValueError('existing draft database required')
            self.db = sqlite3.connect(path.resolve().as_uri()+'?mode=rw', uri=True,
                                      timeout=5, isolation_level=None)
        else:
            self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            if existing_only and self.db.execute('SELECT type FROM sqlite_master WHERE name=?',
                    ('operator_drafts_v1',)).fetchone() != ('table',):
                raise ValueError('existing draft storage schema missing')
            self.db.execute('PRAGMA trusted_schema=OFF')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS operator_drafts_v1('
                            'draft_id TEXT PRIMARY KEY,payload TEXT NOT NULL,digest TEXT NOT NULL)')
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def _guard_write(self):
        if self.db.execute("SELECT type FROM main.sqlite_master WHERE name=? COLLATE NOCASE",
                           ('operator_drafts_v1',)).fetchone() != ('table',):
            raise ValueError('draft storage schema missing')
        if self.db.execute("SELECT 1 FROM sqlite_temp_master WHERE name=? COLLATE NOCASE "
                           "AND type IN ('table','view') LIMIT 1", ('operator_drafts_v1',)).fetchone() is not None:
            raise ValueError('unexpected draft storage shadow')
        for catalog in ('main.sqlite_master', 'sqlite_temp_master'):
            if self.db.execute("SELECT 1 FROM "+catalog+" WHERE type='trigger' "
                               "AND tbl_name=? COLLATE NOCASE LIMIT 1", ('operator_drafts_v1',)).fetchone() is not None:
                raise ValueError('unexpected draft storage trigger')

    def _read(self, key):
        row = self.db.execute('SELECT payload,digest FROM main.operator_drafts_v1 WHERE draft_id=?', (_hash(key),)).fetchone()
        return None if row is None else _decode(key, *row)

    def _encoded(self, record):
        payload = _json(record)
        digest = _digest(payload)
        _decode(record['draft']['draft_id'], payload, digest)
        return payload, digest

    def get(self, key, *, halted=None):
        _permit(halted)
        record = self._read(key)
        return None if record is None else _view(record)

    def list_plan(self, plan_id, *, limit=100, halted=None):
        """Bounded historical projection; validate each returned immutable record."""
        _permit(halted)
        _hash(plan_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid draft history limit')
        rows = self.db.execute("""SELECT draft_id,payload,digest FROM main.operator_drafts_v1
            WHERE json_extract(payload,'$.draft.request.plan_id')=?
            ORDER BY json_extract(payload,'$.created_at') DESC,draft_id LIMIT ?""",
            (plan_id,limit+1)).fetchall()
        records = [_view(_decode(*row)) for row in rows]
        if any(row['draft']['request']['plan_id'] != plan_id for row in records):
            raise ValueError('draft history scope mismatch')
        return dict(plan_id=plan_id, rows=records[:limit], truncated=len(records)>limit,
                    historical_only=True, **dict.fromkeys(_FLAGS,False))

    def save(self, draft, *, now, halted=None):
        _permit(halted)
        draft = _validated(draft)
        key = draft['draft_id']
        stamp = _stamp(now)
        with self._transaction():
            self._guard_write()
            record = self._read(key)
            if record is not None:
                if stamp < (record['acknowledged_at'] or record['created_at']):
                    raise ValueError('draft clock moved backward')
                return _view(record)
            if self.db.execute('SELECT COUNT(*) FROM main.operator_drafts_v1').fetchone()[0] >= MAX_DRAFTS:
                raise ValueError('draft capacity review required')
            record = dict(version=1, draft=draft, created_at=stamp, acknowledged_at=None)
            inserted = self.db.execute('INSERT INTO main.operator_drafts_v1 VALUES (?,?,?)', (key, *self._encoded(record)))
            if inserted.rowcount != 1 or self._read(key) != record:
                raise ValueError('draft storage publication mismatch')
            return _view(record)

    def acknowledge(self, key, *, confirmed=None, now, halted=None):
        _permit(halted)
        if confirmed is not True:
            raise PermissionError('explicit local draft acknowledgment required')
        stamp = _stamp(now)
        with self._transaction():
            self._guard_write()
            record = self._read(key)
            if record is None:
                raise ValueError('saved draft unavailable')
            if stamp < (record['acknowledged_at'] or record['created_at']):
                raise ValueError('draft clock moved backward')
            if record['acknowledged_at'] is None:
                record['acknowledged_at'] = stamp
                changed = self.db.execute('UPDATE main.operator_drafts_v1 SET payload=?,digest=? WHERE draft_id=?',
                                          (*self._encoded(record), key))
                if changed.rowcount != 1 or self._read(key) != record:
                    raise ValueError('draft storage publication mismatch')
            return _view(record)
