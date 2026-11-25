"""Scope local RFQ drafts to a saved Scout plan and declared Atlas supplier.

Only local research: neither declaration matching nor a draft acknowledgment
verifies a supplier, buyer, available capacity, price, recipient or authority.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from .operator_drafts import DraftStore, _digest, _hash, _json, _permit, _stamp, prepare_rfq

MAX_SUPPLIER_AGE = timedelta(hours=24)


def _normalize_supplier(raw):
    from .atlas import normalize_party
    return normalize_party(raw)


def supplier_digest(party):
    """Canonical fingerprint of a normalized declared Atlas profile."""
    capacity = format(party.capacity, 'f')
    if '.' in capacity:
        capacity = capacity.rstrip('0').rstrip('.')
    value = dict(version=1, key=party.key, scheme=party.scheme, identifier=party.identifier,
                 name=party.name, roles=party.roles, classifications=party.classifications,
                 regions=party.regions, currency=party.currency, capacity=capacity,
                 source_url=party.source_url, observed_at=_stamp(party.observed_at))
    return _digest(_json(value))


class OperatorScenario:
    """Trusted local adapter; explicit inputs, fixed current archive, no dispatch.

    Cross-database checks bracket writes but do not provide distributed
    atomicity. A committed historical draft or acknowledgment may survive a
    later scope failure; the result is withheld in that case.
    """
    def __init__(self, directory, *, halt_check, clock=None):
        if not callable(halt_check) or (clock is not None and not callable(clock)):
            raise ValueError('trusted halt and clock callbacks required')
        self.directory = Path(directory)
        self.halt_check = halt_check
        self.clock = clock or (lambda:datetime.now(timezone.utc))
        self.path = self.directory / 'operator.sqlite3'

    def _allowed(self):
        _permit(self.halt_check())

    def _time(self):
        now = self.clock()
        _stamp(now)
        return now.astimezone(timezone.utc)

    def _inspect(self, plan_id, now):
        from .scenario_council import ScenarioCouncil
        return ScenarioCouncil(self.directory, halt_check=self.halt_check,
                               clock=lambda:now).inspect(plan_id)

    def _storage(self, *, existing=False):
        if os.path.lexists(self.path):
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError('invalid local Operator database path')
        elif existing:
            raise ValueError('saved draft history unavailable')
        return DraftStore(self.path,existing_only=os.path.lexists(self.path))

    def _prepare(self, plan_id, supplier, *, region, items, now):
        self._allowed()
        _hash(plan_id)
        snapshot = self._inspect(plan_id, now)
        self._allowed()
        if (type(snapshot) is not dict or snapshot.get('plan_id') != plan_id
                or snapshot.get('source_hold') is not None
                or any(snapshot.get(k) is not False for k in
                       ('external_authority','execution_eligible','independently_verified'))):
            raise ValueError('current source and scenario scope required for drafting')
        context = snapshot['context']
        party = _normalize_supplier(supplier)
        if ('supplier' not in party.roles or party.currency != 'USD'
                or party.observed_at > now or now-party.observed_at > MAX_SUPPLIER_AGE):
            raise ValueError('declared supplier role, currency or freshness mismatch')
        raw = dict(plan_id=plan_id, observation_sha256=context['observation_sha256'],
                   profile_revision=context['profile_revision'],
                   supplier=dict(scheme=party.scheme, identifier=party.identifier),
                   supplier_profile_sha256=supplier_digest(party), region=region,
                   currency='USD', items=items)
        draft = prepare_rfq(raw, halted=False)
        request = draft['request']
        codes = {(item['classification']['scheme'], item['classification']['code'])
                 for item in request['items']}
        if request['region'] not in party.regions or not codes.issubset(party.classifications):
            raise ValueError('declared supplier region or classification mismatch')
        self._allowed()
        return draft

    def prepare(self, plan_id, supplier, *, region, items):
        self._allowed()
        return self._prepare(plan_id, supplier, region=region, items=items, now=self._time())

    def _recheck(self, draft, supplier):
        request = draft['request']
        current = self.prepare(request['plan_id'], supplier, region=request['region'], items=request['items'])
        if current != draft:
            raise ValueError('draft scope changed; create a new draft')

    @staticmethod
    def _history_view(record):
        return dict(record, supplier_scope_pinned='supplier_profile_sha256' in record['draft']['request'])

    def save(self, plan_id, supplier, *, region, items):
        self._allowed()
        now = self._time()
        draft = self._prepare(plan_id, supplier, region=region, items=items, now=now)
        self._allowed()
        with self._storage() as store:
            result = store.save(draft, now=now, halted=False)
        self._recheck(draft, supplier)
        return self._history_view(result)

    def history(self, plan_id, draft_id):
        """Exact historical saved draft, including legacy unpinned records."""
        self._allowed()
        _hash(plan_id)
        _hash(draft_id)
        with self._storage(existing=True) as store:
            result = store.get(draft_id, halted=False)
        self._allowed()
        if result is None or result['draft']['request']['plan_id'] != plan_id:
            raise ValueError('saved draft outside selected plan')
        return self._history_view(result)

    def history_list(self, plan_id, *, limit=100):
        self._allowed()
        _hash(plan_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('invalid draft history limit')
        if not os.path.lexists(self.path):
            from .operator_drafts import _FLAGS
            result = dict(plan_id=plan_id,rows=[],truncated=False,historical_only=True,
                          **dict.fromkeys(_FLAGS,False))
        else:
            with self._storage(existing=True) as store:
                result = store.list_plan(plan_id,limit=limit,halted=False)
            result['rows'] = [self._history_view(row) for row in result['rows']]
        self._allowed()
        return result

    def acknowledge(self, plan_id, draft_id, supplier, *, confirmed=None):
        self._allowed()
        if confirmed is not True:
            raise PermissionError('explicit local draft acknowledgment required')
        record = self.history(plan_id, draft_id)
        if not record['supplier_scope_pinned']:
            raise ValueError('legacy unpinned draft requires a newly scoped draft')
        draft = record['draft']
        self._recheck(draft, supplier)
        now = self._time()
        self._allowed()
        with self._storage(existing=True) as store:
            result = store.acknowledge(draft_id, confirmed=True, now=now, halted=False)
        self._recheck(draft, supplier)
        return self._history_view(result)

    def _recipient_candidate(self,plan_id,draft_id,supplier,recipient,evidence_path):
        self._allowed()
        from .operator_recipients import validate_declaration,prepare_recipient
        from .evidence import fingerprint
        record=self.history(plan_id,draft_id)
        draft=record["draft"]
        if not record["supplier_scope_pinned"]:
            raise ValueError("recipient declaration requires a scoped RFQ")
        self._recheck(draft,supplier)
        party=_normalize_supplier(supplier)
        # Reject malformed declarations before opening the explicitly selected file.
        validate_declaration(draft,recipient,organization_name=party.name,now=self._time(),halted=False)
        evidence=fingerprint(evidence_path,halted=self.halt_check(),halt_check=self.halt_check)
        self._recheck(draft,supplier)
        candidate=prepare_recipient(draft,recipient,organization_name=party.name,
            evidence_reference=evidence,now=self._time(),halted=False)
        self._allowed()
        return draft,candidate

    def recipient_preview(self,plan_id,draft_id,supplier,recipient,evidence_path):
        """Local inspection/fingerprint only, no contact record saved."""
        _,candidate=self._recipient_candidate(plan_id,draft_id,supplier,recipient,evidence_path)
        return candidate

    def recipient_save(self,plan_id,draft_id,supplier,recipient,evidence_path,expected_recipient_id,*,confirmed=None):
        self._allowed()
        if confirmed is not True:
            raise PermissionError("explicit local recipient-record confirmation required")
        _hash(expected_recipient_id)
        draft,candidate=self._recipient_candidate(plan_id,draft_id,supplier,recipient,evidence_path)
        if candidate["recipient_id"]!=expected_recipient_id:
            raise ValueError("recipient evidence or declaration changed; preview again")
        from .operator_recipients import RecipientStore
        path=self.directory/"operator-recipients.sqlite3"
        self._allowed()
        with RecipientStore(path,existing_only=os.path.lexists(path)) as store:
            result=store.save(draft,candidate,now=self._time(),confirmed=True,halted=False)
        # Separate stores: a historical record can survive a post-commit scope failure.
        self._recheck(draft,supplier)
        self._allowed()
        return result

    def recipient_history(self,plan_id,draft_id,*,limit=100):
        self._allowed()
        from .operator_recipients import RecipientStore,_scope,_FLAGS_EXTRA
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid recipient history limit")
        record=self.history(plan_id,draft_id)
        draft=record["draft"]
        scope=_scope(draft)
        path=self.directory/"operator-recipients.sqlite3"
        if not os.path.lexists(path):
            result=dict(scope=scope,rows=[],truncated=False,historical_only=True,
                **dict.fromkeys(_FLAGS_EXTRA,False))
        else:
            with RecipientStore(path,existing_only=True) as store:
                result=store.list_draft(draft,limit=limit,halted=False)
        self._allowed()
        return result
