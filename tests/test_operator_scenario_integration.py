"""Hosted integration against real archive, Atlas and runtime implementations."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_store import ScenarioStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.operator_scenarios import OperatorScenario
from nexus_exchange.operator_drafts import render_rfq
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
from test_operator_scenarios import items
import test_sam_search as sam


class OperatorRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name)
        self.now=NOW
        self.declared=profile()
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        with ProfileStore(self.directory/'owner-profile.sqlite3') as store:
            store.save(self.declared,halted=False)
        with ScenarioStore(self.directory/'scout-leads.sqlite3') as store:
            store.record(self.report,now=NOW,halted=False)
            lead=store.browse(now=NOW,source='sam',profile=self.declared,halted=False)['leads'][0]
            self.context=context_for(lead)
            self.key=store.save(self.context,scenario(),plan(),profile=self.declared,now=NOW,halted=False)
        self.guard=RuntimeGuard(self.directory,clock=lambda:self.now)
        self.addCleanup(self.guard.close)

    def supplier(self, **changes):
        return dict(dict(scheme='REGISTRY',identifier='SYNTHETIC-1',name='Synthetic supplier',
            roles=['supplier'],classifications=[dict(scheme='NAICS',code='518210')],
            regions=['US-CA'],currency='USD',capacity='1000.00',
            source_url='https://example.org/synthetic',observed_at=self.now.isoformat()),**changes)

    def call(self, operation='save', **changes):
        args=dict(supplier=self.supplier(),region='US-CA',items=items())
        args.update(changes)
        return self.guard.operator_action(operation,self.key,**args)

    def test_real_archive_scope_and_local_acknowledgment(self):
        self.guard.resume()
        draft=self.call('prepare')
        self.assertEqual(draft['request']['observation_sha256'],self.context['observation_sha256'])
        self.assertEqual(draft['request']['profile_revision'],self.context['profile_revision'])
        self.assertIn('DRAFT ONLY',render_rfq(draft,halted=False))
        self.assertFalse((self.directory/'operator.sqlite3').exists())
        saved=self.call()
        self.assertEqual(saved['draft'],draft)
        key=draft['draft_id']
        result=self.guard.operator_action('acknowledge',self.key,draft_id=key,
                                          supplier=self.supplier(),confirmed=True)
        self.assertEqual(result['state'],'LOCALLY_ACKNOWLEDGED_DRAFT_ONLY')
        self.assertFalse(result['external_authority'])
        self.assertFalse(result['recipient_verified'])
        self.assertEqual(result,self.guard.operator_action('history',self.key,draft_id=key))

    def test_superseded_observation_and_profile_block_new_drafts(self):
        self.guard.resume()
        saved=self.call()['draft']['draft_id']
        with ProfileStore(self.directory/'owner-profile.sqlite3') as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.call()
        with ProfileStore(self.directory/'owner-profile.sqlite3') as store:
            store.save(self.declared,halted=False)
        self.now+=timedelta(minutes=1)
        updated=copy.deepcopy(self.report)
        updated['leads'][0]['retrieved_at']=self.now.isoformat()
        with ScenarioStore(self.directory/'scout-leads.sqlite3') as store:
            store.record(updated,now=self.now,halted=False)
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual(self.guard.operator_action('history',self.key,draft_id=saved)['state'],'DRAFT_ONLY')

    def test_real_atlas_role_scope_and_stale_source(self):
        self.guard.resume()
        for supplier in (self.supplier(roles=['buyer']),self.supplier(currency='EUR'),
                         self.supplier(classifications=[dict(scheme='CPV',code='518210')])):
            with self.assertRaises(ValueError):
                self.call(supplier=supplier)
        self.assertFalse((self.directory/'operator.sqlite3').exists())
        self.now+=timedelta(days=2)
        with self.assertRaises(ValueError):
            self.call()

    def test_runtime_excludes_halt_workers_threads_and_external_operations(self):
        with self.assertRaises(PermissionError):
            self.call('prepare')
        self.guard.resume()
        with self.assertRaises(ValueError):
            self.guard.operator_action('send',self.key,recipient='not-permitted')
        with self.assertRaises(ValueError):
            self.call(recipient='not-permitted')
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(PermissionError):
                pool.submit(self.call,'prepare').result(timeout=5)
        event=dict(task_id='worker',target='Synthetic',timestamp=self.now.isoformat())
        self.guard.events.append(dict(event,state='queued'))
        with self.assertRaises(PermissionError):
            self.call('prepare')
        self.guard.events.append(dict(event,state='cancelled'))
        original=OperatorScenario.prepare
        def nested(adapter,plan_id,**kwargs):
            with self.assertRaises(PermissionError):
                self.call('prepare')
            with self.assertRaises(PermissionError):
                self.guard.close()
            return original(adapter,plan_id,**kwargs)
        with patch.object(OperatorScenario,'prepare',nested):
            self.assertEqual(self.call('prepare')['request']['plan_id'],self.key)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.call('prepare')
