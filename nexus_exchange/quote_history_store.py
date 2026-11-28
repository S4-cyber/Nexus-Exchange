"""Bounded local receipt retention on a caller-owned SQLite connection.

Not wired into RuntimeGuard, backup or the UI. Receipts are historical data,
not authenticated source evidence or permission. Logical deletion does not
remove exported files, backups or all recoverable disk bytes.
"""
from contextlib import contextmanager
import re

from .quote_history import inspect_receipt, MAX_RECEIPT_BYTES
from .quote_history_lineage import annotate_history, MAX_INDEX_RECEIPTS

_TABLE = 'quote_history_v1'
_SCHEMA = ('CREATE TABLE quote_history_v1(receipt_sha256 TEXT PRIMARY KEY NOT NULL,'
           'plan_id TEXT NOT NULL,payload BLOB NOT NULL)')


def _identifier(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('invalid historical identity')
    return value


class QuoteHistoryStore:
    """Internal storage candidate; caller owns connection and trusted halt check.

    Use a dedicated local database, not an imported database or shared tenancy.
    The caller must establish filesystem safety, recovery and backup policy.
    """
    def __init__(self, db, *, permit):
        self.db = db
        self.permit = permit
        with self._transaction():
            if self.db.execute('SELECT 1 FROM main.sqlite_master WHERE name=? COLLATE NOCASE',
                               (_TABLE,)).fetchone() is None:
                self.db.execute(_SCHEMA)
            self._snapshot()

    @contextmanager
    def _transaction(self):
        self.permit()
        if self.db.in_transaction:
            raise ValueError('independent history transaction required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.permit()
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def _snapshot(self):
        schema = self.db.execute('SELECT type,sql FROM main.sqlite_master WHERE name=? COLLATE NOCASE',
                                 (_TABLE,)).fetchone()
        if schema != ('table', _SCHEMA):
            raise ValueError('unexpected history schema')
        if self.db.execute('SELECT 1 FROM sqlite_temp_master WHERE name=? COLLATE NOCASE',
                           (_TABLE,)).fetchone() is not None:
            raise ValueError('unexpected history shadow')
        for catalog in ('main.sqlite_master', 'sqlite_temp_master'):
            if self.db.execute('SELECT 1 FROM '+catalog+' WHERE type=\'trigger\' '
                               'AND tbl_name=? COLLATE NOCASE', (_TABLE,)).fetchone() is not None:
                raise ValueError('unexpected history trigger')
        rows = self.db.execute('SELECT receipt_sha256,plan_id,CASE WHEN typeof(payload)=\'blob\' '
                               'AND length(payload) BETWEEN 1 AND ? THEN payload END '
                               'FROM main.quote_history_v1 LIMIT ?',
                               (MAX_RECEIPT_BYTES, MAX_INDEX_RECEIPTS+1)).fetchall()
        if len(rows) > MAX_INDEX_RECEIPTS:
            raise ValueError('history capacity exceeded')
        result = {}
        for key, plan, payload in rows:
            item = self._inspect(payload)
            if key != item['receipt_sha256'] or plan != item['plan_id'] or key in result:
                raise ValueError('stored history identity mismatch')
            result[key] = (plan, payload, item)
        return result

    @staticmethod
    def _inspect(payload):
        if type(payload) is not bytes or not 1 <= len(payload) <= MAX_RECEIPT_BYTES:
            raise ValueError('bounded receipt bytes required')
        item = inspect_receipt(payload)
        _identifier(item['receipt_sha256'])
        _identifier(item['plan_id'])
        return item

    @staticmethod
    def _view(snapshot, plan):
        return annotate_history([item for owner, _, item in snapshot.values() if owner == plan])

    def list_plan(self, plan):
        plan = _identifier(plan)
        with self._transaction():
            return self._view(self._snapshot(), plan)

    def retain(self, plan, documents, *, confirmed=None):
        if confirmed is not True:
            raise PermissionError('explicit local history retention required')
        plan = _identifier(plan)
        if type(documents) is not list or not 1 <= len(documents) <= MAX_INDEX_RECEIPTS:
            raise ValueError('bounded receipt batch required')
        with self._transaction():
            expected = self._snapshot()
            for payload in documents:
                item = self._inspect(payload)
                key = item['receipt_sha256']
                if item['plan_id'] != plan:
                    raise ValueError('receipt outside selected plan')
                record = (plan, payload, item)
                if key in expected:
                    if expected[key] != record:
                        raise ValueError('conflicting historical receipt')
                    continue
                if len(expected) >= MAX_INDEX_RECEIPTS:
                    raise ValueError('history capacity review required')
                changed = self.db.execute('INSERT INTO main.quote_history_v1 VALUES (?,?,?)',
                                          (key, plan, payload))
                if changed.rowcount != 1:
                    raise ValueError('history publication mismatch')
                expected[key] = record
            if self._snapshot() != expected:
                raise ValueError('history publication mismatch')
            return self._view(expected, plan)

    def forget(self, plan, receipt_ids, *, confirmed=None):
        if confirmed is not True:
            raise PermissionError('explicit local history deletion required')
        plan = _identifier(plan)
        if type(receipt_ids) is not list or not 1 <= len(receipt_ids) <= MAX_INDEX_RECEIPTS:
            raise ValueError('bounded receipt identity batch required')
        keys = {_identifier(key) for key in receipt_ids}
        if len(keys) != len(receipt_ids):
            raise ValueError('duplicate deletion identity')
        with self._transaction():
            expected = self._snapshot()
            if any(key not in expected or expected[key][0] != plan for key in keys):
                raise ValueError('receipt outside selected plan or missing')
            for key in keys:
                changed = self.db.execute('DELETE FROM main.quote_history_v1 WHERE receipt_sha256=? AND plan_id=?',
                                          (key, plan))
                if changed.rowcount != 1:
                    raise ValueError('history deletion mismatch')
                del expected[key]
            if self._snapshot() != expected:
                raise ValueError('history deletion mismatch')
            return self._view(expected, plan)
