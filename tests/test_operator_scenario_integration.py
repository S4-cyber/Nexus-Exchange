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

    def test_runtime_scoped_history_listing_and_halt(self):
        self.guard.resume()
        empty=self.guard.operator_action('history_list',self.key,limit=100)
        self.assertEqual(empty['rows'],[])
        self.assertFalse((self.directory/'operator.sqlite3').exists())
        first=self.call()
        second=self.call(supplier=self.supplier(identifier='SYNTHETIC-2'))
        result=self.guard.operator_action('history_list',self.key,limit=1)
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['rows']),1)
        result=self.guard.operator_action('history_list',self.key,limit=100)
        self.assertEqual({row['draft']['draft_id'] for row in result['rows']},
                         {first['draft']['draft_id'],second['draft']['draft_id']})
        self.assertTrue(result['historical_only'])
        self.assertFalse(result['current_decision'])
        with ProfileStore(self.directory/'owner-profile.sqlite3') as store:
            store.save(profile(hours_per_week=30),halted=False)
        self.assertEqual(self.guard.operator_action('history_list',self.key,limit=100),result)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.guard.operator_action('history_list',self.key,limit=100)

    def test_recipient_runtime_bound_to_exact_draft_and_file(self):
        self.guard.resume()
        draft=self.call()["draft"]
        key=draft["draft_id"]
        path=self.directory/"synthetic-recipient-evidence.txt"
        path.write_bytes(b"synthetic public contact evidence")
        recipient=dict(scheme="REGISTRY",identifier="SYNTHETIC-1",organization_name="Synthetic supplier",
            email="quotes@example.org",source_url="https://example.org/contact",observed_at=self.now.isoformat())
        args=dict(draft_id=key,supplier=self.supplier(),recipient=recipient,evidence_path=path)
        preview=self.guard.operator_action("recipient_preview",self.key,**args)
        self.assertFalse(preview["recipient_verified"])
        self.assertFalse((self.directory/"operator-recipients.sqlite3").exists())
        self.assertEqual(self.guard.operator_action("recipient_history",self.key,draft_id=key,limit=100)["rows"],[])
        path.write_bytes(b"changed evidence")
        with self.assertRaises(ValueError):
            self.guard.operator_action("recipient_save",self.key,**args,
                expected_recipient_id=preview["recipient_id"],confirmed=True)
        self.assertFalse((self.directory/"operator-recipients.sqlite3").exists())
        path.write_bytes(b"synthetic public contact evidence")
        saved=self.guard.operator_action("recipient_save",self.key,**args,
            expected_recipient_id=preview["recipient_id"],confirmed=True)
        self.assertEqual(saved["candidate"],preview)
        self.assertNotIn(str(path),str(saved))
        self.assertFalse(saved["send_enabled"])
        rows=self.guard.operator_action("recipient_history",self.key,draft_id=key,limit=100)
        self.assertEqual(rows["rows"],[saved])
        self.assertEqual(self.guard.operator_action("recipient_history",self.key,
            draft_id=self.call(supplier=self.supplier(identifier="SYNTHETIC-2"))["draft"]["draft_id"],limit=100)["rows"],[])
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.guard.operator_action("recipient_preview",self.key,**args)
        self.assertEqual(self.guard.operator_action("recipient_history",self.key,draft_id=key,limit=100),rows)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.guard.operator_action("recipient_history",self.key,draft_id=key,limit=100)

    def test_recipient_malformed_declaration_denied_before_file_and_no_send(self):
        self.guard.resume()
        key=self.call()["draft"]["draft_id"]
        args=dict(draft_id=key,supplier=self.supplier(),
            recipient=dict(scheme="REGISTRY",identifier="OTHER",organization_name="Other",
                email="quotes@example.org",source_url="https://example.org/contact",observed_at=self.now.isoformat()),
            evidence_path=self.directory/"missing")
        with patch("nexus_exchange.evidence.fingerprint") as reader:
            with self.assertRaises(ValueError):
                self.guard.operator_action("recipient_preview",self.key,**args)
            reader.assert_not_called()
        with self.assertRaises(PermissionError):
            self.guard.operator_action("recipient_save",self.key,**args,
                expected_recipient_id="a"*64,confirmed=False)
        with self.assertRaises(ValueError):
            self.guard.operator_action("recipient_send",self.key,draft_id=key)


    def test_durable_thread_runtime_scope_evidence_and_halt(self):
        from nexus_exchange.evidence import fingerprint
        self.guard.resume()
        draft=self.call()["draft"]
        key=draft["draft_id"]
        supplier=self.supplier()
        path=self.directory/"synthetic-thread-evidence.txt"
        path.write_bytes(b"synthetic contact evidence")
        recipient=dict(scheme="REGISTRY",identifier="SYNTHETIC-1",organization_name="Synthetic supplier",
            email="quotes@example.org",source_url="https://example.org/contact",observed_at=self.now.isoformat())
        args=dict(draft_id=key,supplier=supplier,recipient=recipient,evidence_path=path)
        preview=self.guard.operator_action("recipient_preview",self.key,**args)
        self.guard.operator_action("recipient_save",self.key,**args,
            expected_recipient_id=preview["recipient_id"],confirmed=True)
        scope=dict(draft_id=key,recipient_id=preview["recipient_id"])
        self.assertIsNone(self.guard.operator_action("thread_history",self.key,**scope))
        self.assertFalse((self.directory/"operator-threads.sqlite3").exists())
        opened=self.guard.operator_action("thread_open",self.key,**scope,supplier=supplier,confirmed=True)
        path.write_bytes(b"synthetic reply")
        reference=fingerprint(path,halted=False)
        event=dict(**scope,supplier=supplier,kind="SIMULATED_REPLY",evidence_path=path,
                   expected_head=opened["head_sha256"],expected_evidence=reference,confirmed=True)
        path.write_bytes(b"changed reply")
        with self.assertRaises(ValueError):
            self.guard.operator_action("thread_append",self.key,**event)
        path.write_bytes(b"synthetic reply")
        updated=self.guard.operator_action("thread_append",self.key,**event)
        self.assertEqual(len(updated["events"]),1)
        self.assertFalse(updated["reply_authenticated"])
        self.assertNotIn(str(path),str(updated))
        with self.assertRaises(ValueError):
            self.guard.operator_action("thread_append",self.key,**event)
        self.assertEqual(self.guard.operator_action("thread_open",self.key,**scope,supplier=supplier,
            confirmed=True),updated)
        self.assertEqual(self.guard.operator_action("thread_history",self.key,**scope),updated)
        with self.assertRaises(ValueError):
            self.guard.operator_action("thread_history",self.key,draft_id=key,recipient_id="a"*64)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.guard.operator_action("thread_history",self.key,**scope)

    def test_thread_runtime_rejects_suppressed_append_and_preserves_history(self):
        import sqlite3
        from contextlib import closing
        from nexus_exchange.evidence import fingerprint
        self.guard.resume()
        key=self.call()["draft"]["draft_id"]
        supplier=self.supplier()
        path=self.directory/"thread-runtime-fixture.txt"
        path.write_bytes(b"synthetic contact evidence")
        recipient=dict(scheme="REGISTRY",identifier="SYNTHETIC-1",
            organization_name="Synthetic supplier",email="quotes@example.org",
            source_url="https://example.org/contact",observed_at=self.now.isoformat())
        args=dict(draft_id=key,supplier=supplier,recipient=recipient,evidence_path=path)
        preview=self.guard.operator_action("recipient_preview",self.key,**args)
        self.guard.operator_action("recipient_save",self.key,**args,
            expected_recipient_id=preview["recipient_id"],confirmed=True)
        scope=dict(draft_id=key,recipient_id=preview["recipient_id"])
        opened=self.guard.operator_action("thread_open",self.key,**scope,supplier=supplier,confirmed=True)
        path.write_bytes(b"synthetic response")
        event=dict(**scope,supplier=supplier,kind="SIMULATED_REPLY",evidence_path=path,
                   expected_head=opened["head_sha256"],expected_evidence=fingerprint(path,halted=False),
                   confirmed=True)
        db_path=self.directory/"operator-threads.sqlite3"
        with closing(sqlite3.connect(db_path,isolation_level=None)) as db:
            db.execute("CREATE TRIGGER bad BEFORE UPDATE ON operator_threads_v1 "
                       "BEGIN SELECT RAISE(IGNORE); END")
            try:
                with self.assertRaises(ValueError):
                    self.guard.operator_action("thread_append",self.key,**event)
                self.assertEqual(self.guard.operator_action("thread_history",self.key,**scope),opened)
            finally:
                db.execute("DROP TRIGGER bad")
        updated=self.guard.operator_action("thread_append",self.key,**event)
        self.assertEqual(len(updated["events"]),1)
        self.assertFalse(updated["delivery_verified"])
        self.assertFalse(updated["reply_authenticated"])
        self.assertFalse(updated["send_enabled"])
        self.assertEqual(self.guard.operator_action("thread_history",self.key,**scope),updated)
