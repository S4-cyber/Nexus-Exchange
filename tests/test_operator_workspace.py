import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange.operator_drafts import DraftStore, prepare_rfq
from nexus_exchange.operator_scenarios import OperatorScenario
from nexus_exchange.operator_workspace import OperatorWorkspace, parse_supplier, parse_items, record_text

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
PLAN = 'a'*64


def fields():
    return dict(scheme='REGISTRY', identifier='SYNTHETIC-1', name='Synthetic supplier',
                classifications='NAICS:518210, CPV:72', regions='US-CA, US-NY',
                capacity='1000.00', source_url='https://example.org/registry',
                observed_at=NOW.isoformat())


def lines():
    return 'Document indexing | 10 | hour | NAICS | 518210'


def draft(plan_id=PLAN, *, pinned=True, region='US-CA'):
    raw=dict(plan_id=plan_id,observation_sha256='b'*64,profile_revision='c'*64,
             supplier=dict(scheme='REGISTRY',identifier='SYNTHETIC-1'),region=region,
             currency='USD',items=parse_items(lines()))
    if pinned:
        raw['supplier_profile_sha256']='d'*64
    return prepare_rfq(raw,halted=False)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.blocked=False
        self.action=Mock()
        self.workspace=OperatorWorkspace(PLAN,action=self.action,blocked_check=lambda:self.blocked)

    def test_explicit_fields_and_items(self):
        party=parse_supplier(fields())
        self.assertEqual(party['roles'],['supplier'])
        self.assertEqual(party['currency'],'USD')
        self.assertEqual(party['classifications'],[dict(scheme='NAICS',code='518210'),dict(scheme='CPV',code='72')])
        self.assertEqual(party['regions'],['US-CA','US-NY'])
        self.assertEqual(parse_items(lines())[0]['quantity'],'10')
        self.assertEqual(len(parse_items('\n'.join([lines()]*16))),16)
        self.action.assert_not_called()

    def test_bad_forms_never_dispatch(self):
        for value in ('', 'missing fields', '\n'.join([lines()]*17), 'x'*16385,
                      'bad | 1 | hour | NAICS | ', 'bad\tvalue | 1 | hour | NAICS | 1'):
            with self.assertRaises(ValueError):
                self.workspace.prepare(fields(),'US-CA',value)
        for changes in (dict(classifications='NAICS'),dict(regions=''),dict(source_url=''),dict(recipient='x')):
            with self.assertRaises(ValueError):
                self.workspace.prepare(dict(fields(),**changes),'US-CA',lines())
        self.action.assert_not_called()

    def test_preview_is_separate_from_save_and_scope(self):
        self.action.return_value=draft()
        result=self.workspace.prepare(fields(),'US-CA',lines())
        self.assertEqual(result,draft())
        self.action.assert_called_once_with('prepare',PLAN,supplier=parse_supplier(fields()),region='US-CA',items=parse_items(lines()))
        self.action.return_value=draft('e'*64)
        with self.assertRaises(ValueError):
            self.workspace.prepare(fields(),'US-CA',lines())
        self.action.return_value=dict(draft(),send_enabled=True)
        with self.assertRaises(ValueError):
            self.workspace.prepare(fields(),'US-CA',lines())

    def test_save_and_history_exact_record(self):
        with DraftStore(self.directory/'operator.sqlite3') as store:
            rec=store.save(draft(),now=NOW,halted=False)
        self.action.return_value=dict(rec,supplier_scope_pinned=True)
        saved=self.workspace.save(fields(),'US-CA',lines())
        self.assertIn('HISTORICAL ONLY',record_text(saved))
        self.assertIn('DRAFT ONLY',record_text(saved))
        self.assertIn('No current decision',record_text(saved))
        self.assertEqual(saved,self.workspace.history(draft()['draft_id']))
        with self.assertRaises(ValueError):
            self.workspace.history('e'*64)
        self.action.return_value=dict(saved,current_decision=True)
        with self.assertRaises(ValueError):
            self.workspace.history(draft()['draft_id'])

    def test_ack_requires_literal_confirmation(self):
        with DraftStore(self.directory/'operator.sqlite3') as store:
            store.save(draft(),now=NOW,halted=False)
            rec=store.acknowledge(draft()['draft_id'],confirmed=True,now=NOW,halted=False)
        self.action.return_value=dict(rec,supplier_scope_pinned=True)
        for value in (None,False,1):
            with self.assertRaises(PermissionError):
                self.workspace.acknowledge(draft()['draft_id'],fields(),confirmed=value)
        self.action.assert_not_called()
        result=self.workspace.acknowledge(draft()['draft_id'],fields(),confirmed=True)
        self.assertEqual(result['state'],'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY')
        self.action.assert_called_once_with('acknowledge',PLAN,draft_id=draft()['draft_id'],supplier=parse_supplier(fields()),confirmed=True)

    def test_blocked_before_and_after_call(self):
        for value in (None,0,True):
            self.blocked=value
            for call in (lambda:self.workspace.prepare(fields(),'US-CA',lines()),lambda:self.workspace.save(fields(),'US-CA',lines()),
                         self.workspace.history_list,lambda:self.workspace.history('a'*64),lambda:self.workspace.acknowledge('a'*64,fields(),confirmed=True)):
                with self.assertRaises(PermissionError):
                    call()
        self.action.assert_not_called()
        self.blocked=False
        def changed(*args,**kwargs):
            self.blocked=True
            return draft()
        self.action.side_effect=changed
        with self.assertRaises(PermissionError):
            self.workspace.prepare(fields(),'US-CA',lines())

    def test_plan_history_listing_bounds_and_scope(self):
        with DraftStore(self.directory/'operator.sqlite3') as store:
            for item in (draft(),draft(region='US-NY'),draft('e'*64),draft(pinned=False)):
                store.save(item,now=NOW,halted=False)
            result=store.list_plan(PLAN,limit=2,halted=False)
            self.assertTrue(result['truncated'])
            self.assertEqual(len(result['rows']),2)
            result=store.list_plan(PLAN,limit=100,halted=False)
            self.assertFalse(result['truncated'])
            self.assertEqual(len(result['rows']),3)
            self.assertTrue(all(row['draft']['request']['plan_id']==PLAN for row in result['rows']))
            self.assertFalse(result['external_authority'])
            for limit in (True,0,101):
                with self.assertRaises(ValueError):
                    store.list_plan(PLAN,limit=limit,halted=False)
            with self.assertRaises(PermissionError):
                store.list_plan(PLAN,halted=True)

    def test_listing_detects_tampered_record_and_missing_schema(self):
        path=self.directory/'operator.sqlite3'
        with DraftStore(path) as store:
            store.save(draft(),now=NOW,halted=False)
            store.db.execute("UPDATE operator_drafts_v1 SET digest='bad'")
            with self.assertRaises(ValueError):
                store.list_plan(PLAN,halted=False)
            store.db.execute('DROP TABLE operator_drafts_v1')
        with self.assertRaises(ValueError):
            DraftStore(path,existing_only=True)

    def test_missing_history_list_creates_no_database(self):
        adapter=OperatorScenario(self.directory,halt_check=lambda:False,clock=lambda:NOW)
        result=adapter.history_list(PLAN,limit=100)
        self.assertEqual(result['rows'],[])
        self.assertFalse(result['truncated'])
        self.assertFalse((self.directory/'operator.sqlite3').exists())
        self.action.return_value=result
        self.assertEqual(self.workspace.history_list(),result)
        self.action.assert_called_once_with('history_list',PLAN,limit=100)

    def test_historical_legacy_cannot_be_presented_as_scoped(self):
        path=self.directory/'operator.sqlite3'
        with DraftStore(path) as store:
            store.save(draft(pinned=False),now=NOW,halted=False)
        adapter=OperatorScenario(self.directory,halt_check=lambda:False,clock=lambda:NOW)
        result=adapter.history_list(PLAN,limit=100)
        self.assertFalse(result['rows'][0]['supplier_scope_pinned'])
        self.assertIn('Legacy unpinned',record_text(result['rows'][0]))
        self.action.return_value=result
        self.assertEqual(self.workspace.history_list(),result)
        result['rows'][0]['supplier_scope_pinned']=True
        with self.assertRaises(ValueError):
            self.workspace.history_list()
