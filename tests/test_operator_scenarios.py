import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nexus_exchange.operator_drafts import DraftStore, prepare_rfq
from nexus_exchange.operator_scenarios import OperatorScenario, supplier_digest

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
PLAN = 'a'*64
OBS = 'b'*64
PROFILE = 'c'*64


def party(**kw):
    values = dict(key='d'*64, scheme='REGISTRY', identifier='SYNTHETIC-1',
                  name='Synthetic supplier', roles=('supplier',),
                  classifications=(('NAICS','518210'),), regions=('US-CA',),
                  currency='USD', capacity=Decimal('1000.00'),
                  source_url='https://example.org/private-source', observed_at=NOW)
    values.update(kw)
    return SimpleNamespace(**values)


def items():
    return [dict(description='Document indexing', quantity='10.00', unit='hour',
                 classification=dict(scheme='NAICS',code='518210'))]


def snapshot(**kw):
    result = dict(plan_id=PLAN, context=dict(observation_sha256=OBS,profile_revision=PROFILE),
                  source_hold=None, external_authority=False, execution_eligible=False,
                  independently_verified=False)
    result.update(kw)
    return result


class OperatorScenarioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.now = NOW
        self.halted = False
        self.adapter = OperatorScenario(self.directory, halt_check=lambda:self.halted, clock=lambda:self.now)
        inspector = patch.object(self.adapter, '_inspect', return_value=snapshot())
        self.inspect = inspector.start()
        self.addCleanup(inspector.stop)
        normalizer = patch('nexus_exchange.operator_scenarios._normalize_supplier', return_value=party())
        self.normalize = normalizer.start()
        self.addCleanup(normalizer.stop)

    def prepare(self, **kw):
        args=dict(region='US-CA',items=items()); args.update(kw)
        return self.adapter.prepare(PLAN, {}, **args)

    def save(self):
        return self.adapter.save(PLAN, {}, region='US-CA', items=items())

    def acknowledge(self, key, confirmed=True):
        return self.adapter.acknowledge(PLAN,key,{},confirmed=confirmed)

    def test_prepare_binds_archive_and_supplier_without_writes(self):
        draft=self.prepare()
        self.assertEqual(draft['format'],'nexus-operator-rfq-v2')
        self.assertEqual(draft['request']['observation_sha256'],OBS)
        self.assertEqual(draft['request']['profile_revision'],PROFILE)
        self.assertEqual(draft['request']['supplier_profile_sha256'],supplier_digest(party()))
        self.assertEqual(draft['request']['items'][0]['quantity'],'10')
        self.assertFalse(draft['recipient_verified'])
        self.assertFalse(draft['send_enabled'])
        self.assertNotIn('private-source',str(draft))
        self.assertFalse((self.directory/'operator.sqlite3').exists())

    def test_supplier_declaration_revision_changes_draft_identity(self):
        first=self.save()['draft']['draft_id']
        self.acknowledge(first)
        self.normalize.return_value=party(capacity=Decimal('2000'))
        second=self.save()
        self.assertNotEqual(first,second['draft']['draft_id'])
        self.assertEqual(second['state'],'DRAFT_ONLY')
        with self.assertRaises(ValueError):
            self.acknowledge(first)
        self.assertEqual(self.adapter.history(PLAN,first)['state'],'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY')

    def test_supplier_digest_canonical_decimal_and_time(self):
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(supplier_digest(party(capacity=Decimal('12345.6700'))),
                             supplier_digest(party(capacity=Decimal('12345.67'),
                                observed_at=NOW.astimezone(timezone(timedelta(hours=-8))))))

    def test_supplier_role_currency_region_classification_and_freshness(self):
        for changed in (dict(roles=('buyer',)),dict(currency='EUR'),dict(regions=('US-NY',)),
                        dict(classifications=(('CPV','518210'),)),
                        dict(observed_at=NOW-timedelta(hours=24,seconds=1)),
                        dict(observed_at=NOW+timedelta(seconds=1))):
            self.normalize.return_value=party(**changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                self.save()
        self.assertFalse((self.directory/'operator.sqlite3').exists())

    def test_source_hold_and_foreign_context_never_save(self):
        for changed in (dict(source_hold='SOURCE_REVIEW_REQUIRED'),dict(source_hold='CONTRACTOR_INTELLIGENCE_ONLY'),
                        dict(source_hold='SOURCE_NOT_SELECTED'),dict(plan_id='e'*64),
                        dict(external_authority=True),dict(independently_verified=True)):
            self.inspect.return_value=snapshot(**changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                self.save()
        self.assertFalse((self.directory/'operator.sqlite3').exists())

    def test_halt_precedes_archive_or_supplier_access(self):
        for value in (True,None,0):
            self.halted=value
            for operation in (self.prepare,self.save,lambda:self.acknowledge('a'*64),
                              lambda:self.adapter.history(PLAN,'a'*64)):
                with self.assertRaises(PermissionError):
                    operation()
        self.inspect.assert_not_called()
        self.normalize.assert_not_called()

    def test_explicit_ack_and_scope_revalidation(self):
        key=self.save()['draft']['draft_id']
        with self.assertRaises(PermissionError):
            self.acknowledge(key,False)
        self.inspect.return_value=snapshot(context=dict(observation_sha256='f'*64,profile_revision=PROFILE))
        with self.assertRaises(ValueError):
            self.acknowledge(key)
        history=self.adapter.history(PLAN,key)
        self.assertEqual(history['state'],'DRAFT_ONLY')
        self.assertTrue(history['historical_only'])
        self.assertFalse(history['current_decision'])
        with self.assertRaises(ValueError):
            self.adapter.history('e'*64,key)

    def test_legacy_draft_history_not_eligible_for_scoped_ack(self):
        raw=dict(plan_id=PLAN,observation_sha256=OBS,profile_revision=PROFILE,
                 supplier=dict(scheme='REGISTRY',identifier='SYNTHETIC-1'),region='US-CA',currency='USD',items=items())
        draft=prepare_rfq(raw,halted=False)
        with DraftStore(self.directory/'operator.sqlite3') as store:
            store.save(draft,now=NOW,halted=False)
        self.assertFalse(self.adapter.history(PLAN,draft['draft_id'])['supplier_scope_pinned'])
        with self.assertRaises(ValueError):
            self.acknowledge(draft['draft_id'])

    def test_context_drift_after_commit_withholds_result(self):
        self.inspect.side_effect=[snapshot(),snapshot(context=dict(observation_sha256='f'*64,profile_revision=PROFILE))]
        with self.assertRaises(ValueError):
            self.save()
        self.inspect.side_effect=None
        key=self.prepare()['draft_id']
        self.assertEqual(self.adapter.history(PLAN,key)['state'],'DRAFT_ONLY')

    def test_missing_history_does_not_create_storage(self):
        with self.assertRaises(ValueError):
            self.adapter.history(PLAN,'a'*64)
        self.assertFalse((self.directory/'operator.sqlite3').exists())

    def test_valid_scope_acknowledgment_does_not_grant_authority(self):
        key=self.save()['draft']['draft_id']
        result=self.acknowledge(key)
        self.assertEqual(result['state'],'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY')
        for flag in ('external_authority','send_enabled','recipient_verified','reviewer_authenticated','current_decision'):
            self.assertIs(result[flag],False)
        self.assertTrue(result['supplier_scope_pinned'])
