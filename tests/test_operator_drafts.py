import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.operator_drafts import DraftStore, prepare_rfq, render_rfq
from nexus_exchange.governor import Action, decide

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)


def request():
    return dict(plan_id='a'*64, observation_sha256='b'*64, profile_revision='c'*64,
                supplier=dict(scheme='REGISTRY', identifier='SUPPLIER-1'),
                region='US-CA', currency='USD', items=[dict(description='Document indexing',
                quantity='10.00', unit='hour', classification=dict(scheme='NAICS', code='518210'))])


class OperatorDraftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'drafts.sqlite3'

    def prepare(self, raw=None):
        return prepare_rfq(request() if raw is None else raw, halted=False)

    def test_canonical_draft_and_nonbinding_text(self):
        draft = self.prepare()
        self.assertEqual(draft['request']['items'][0]['quantity'], '10')
        self.assertFalse(draft['external_authority'])
        self.assertFalse(draft['recipient_verified'])
        self.assertFalse(draft['send_enabled'])
        text = render_rfq(draft, halted=False)
        for phrase in ('DRAFT ONLY', 'non-binding', 'Document indexing', 'unit price', 'quote validity'):
            self.assertIn(phrase, text)
        self.assertNotIn('SUPPLIER-1', text)  # declared registry identity is not a recipient
        self.assertEqual(draft['draft_id'], self.prepare()['draft_id'])

    def test_scope_and_party_change_identity(self):
        original = self.prepare()['draft_id']
        for field, value in [('plan_id','d'*64),('profile_revision','e'*64),('region','US-NY'),
                             ('supplier',dict(scheme='REGISTRY',identifier='SUPPLIER-2'))]:
            self.assertNotEqual(self.prepare(dict(request(), **{field:value}))['draft_id'], original)

    def test_invalid_requests_rejected(self):
        for changed in [dict(plan_id='é'*64), dict(currency='EUR'), dict(region='US CA'),
                        dict(recipient='example@example.com'), dict(items=[]),
                        dict(supplier=dict(scheme='REGISTRY',identifier='X\nY'))]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.prepare(dict(request(), **changed))
        for field, value in [('quantity','0'),('quantity','1e6'),('quantity',True),
                             ('description','bad\nline'),('description','bad\u202evalue'),
                             ('classification',{'scheme':'NAICS','code':'A','extra':1})]:
            raw = request()
            raw['items'][0][field] = value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                self.prepare(raw)

    def test_payload_tampering_rejected(self):
        draft = self.prepare()
        draft['request']['items'][0]['quantity'] = '11'
        with self.assertRaises(ValueError):
            render_rfq(draft, halted=False)
        with DraftStore(self.path) as store:
            with self.assertRaises(ValueError):
                store.save(draft, now=NOW, halted=False)

    def test_halt_is_fail_closed(self):
        for halted in (None, True, 0):
            with self.assertRaises(PermissionError):
                prepare_rfq(request(), halted=halted)
            with self.assertRaises(PermissionError):
                render_rfq(self.prepare(), halted=halted)
            with DraftStore(self.path) as store:
                with self.assertRaises(PermissionError):
                    store.save(self.prepare(), now=NOW, halted=halted)
                with self.assertRaises(PermissionError):
                    store.get('a'*64, halted=halted)
                with self.assertRaises(PermissionError):
                    store.acknowledge('a'*64, confirmed=True, now=NOW, halted=halted)

    def test_persistent_idempotent_draft_and_acknowledgment(self):
        draft = self.prepare()
        key = draft['draft_id']
        with DraftStore(self.path) as store:
            saved = store.save(draft, now=NOW, halted=False)
            self.assertEqual(saved['state'], 'DRAFT_ONLY')
            self.assertEqual(store.save(draft, now=NOW+timedelta(seconds=1), halted=False), saved)
            for confirmed in (None, False, 1):
                with self.assertRaises(PermissionError):
                    store.acknowledge(key, confirmed=confirmed, now=NOW, halted=False)
            reviewed = store.acknowledge(key, confirmed=True, now=NOW, halted=False)
            self.assertEqual(reviewed['state'], 'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY')
            for flag in ('external_authority','send_enabled','recipient_verified','reviewer_authenticated','current_decision'):
                self.assertFalse(reviewed[flag])
            self.assertFalse(decide(Action.OUTREACH, halted=False).allowed)
        with DraftStore(self.path) as store:
            self.assertEqual(store.get(key, halted=False), reviewed)
            self.assertEqual(store.acknowledge(key, confirmed=True, now=NOW+timedelta(days=1), halted=False), reviewed)

    def test_modified_draft_does_not_inherit_acknowledgment(self):
        first = self.prepare()
        raw = request()
        raw['items'][0]['quantity'] = '20'
        second = self.prepare(raw)
        with DraftStore(self.path) as store:
            store.save(first, now=NOW, halted=False)
            store.acknowledge(first['draft_id'], confirmed=True, now=NOW, halted=False)
            self.assertEqual(store.save(second, now=NOW, halted=False)['state'], 'DRAFT_ONLY')
            self.assertNotEqual(first['draft_id'], second['draft_id'])

    def test_clock_and_rollback(self):
        draft = self.prepare()
        key = draft['draft_id']
        with DraftStore(self.path) as store:
            store.save(draft, now=NOW, halted=False)
            with self.assertRaises(ValueError):
                store.acknowledge(key, confirmed=True, now=NOW-timedelta(seconds=1), halted=False)
            store.db.execute("CREATE TRIGGER reject_ack BEFORE UPDATE ON operator_drafts_v1 BEGIN SELECT RAISE(ABORT,'synthetic'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store.acknowledge(key, confirmed=True, now=NOW, halted=False)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(store.get(key, halted=False)['state'], 'DRAFT_ONLY')

    def test_corrupt_record_and_capacity(self):
        draft = self.prepare()
        with DraftStore(self.path) as store:
            store.save(draft, now=NOW, halted=False)
            with patch('nexus_exchange.operator_drafts.MAX_DRAFTS',1):
                store.save(draft, now=NOW, halted=False)
                with self.assertRaisesRegex(ValueError,'capacity'):
                    store.save(self.prepare(dict(request(),region='US-NY')), now=NOW, halted=False)
            store.db.execute("UPDATE operator_drafts_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.get(draft['draft_id'], halted=False)

    def test_no_unvalidated_recipient_or_commitment_fields(self):
        draft = self.prepare()
        for extra in ('recipient','approved','binding_offer','payment_account'):
            changed = dict(draft, **{extra:'synthetic'})
            with self.assertRaises(ValueError):
                render_rfq(changed, halted=False)
        with DraftStore(self.path) as store:
            self.assertIsNone(store.get(draft['draft_id'], halted=False))
            with self.assertRaises(ValueError):
                store.acknowledge(draft['draft_id'], confirmed=True, now=NOW, halted=False)

    def test_rehashed_payload_cannot_change_draft_id(self):
        import hashlib
        draft = self.prepare()
        with DraftStore(self.path) as store:
            store.save(draft, now=NOW, halted=False)
            payload = json.loads(store.db.execute('SELECT payload FROM operator_drafts_v1').fetchone()[0])
            payload['draft']['request']['region'] = 'US-NY'
            encoded = json.dumps(payload, sort_keys=True, separators=(',',':'), ensure_ascii=True)
            store.db.execute('UPDATE operator_drafts_v1 SET payload=?,digest=?',
                             (encoded,hashlib.sha256(encoded.encode('ascii')).hexdigest()))
            with self.assertRaises(ValueError):
                store.get(draft['draft_id'], halted=False)
