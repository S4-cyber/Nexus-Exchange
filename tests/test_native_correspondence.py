import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from nexus_exchange.operator_workspace import OperatorWorkspace
from nexus_exchange.correspondence_workspace import CorrespondenceWorkspace
from nexus_exchange.operator_recipients import prepare_recipient, _FLAGS_EXTRA
from nexus_exchange.correspondence_thread import open_thread, append_event
from nexus_exchange.evidence import fingerprint
from tempfile import TemporaryDirectory
from pathlib import Path
from test_operator_workspace import PLAN, fields, draft

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
REFERENCE='sha256:'+'a'*64+';bytes:12'

class NativeCorrespondenceTests(unittest.TestCase):
    def setUp(self):
        self.action=Mock()
        self.blocked=False
        self.rfq=draft()
        self.workspace=OperatorWorkspace(PLAN,action=self.action,blocked_check=lambda:self.blocked)
        self.controller=CorrespondenceWorkspace(self.workspace,self.rfq,fields())
        self.contact=self.controller.contact('quotes@example.org','https://example.org/contact',NOW.isoformat())
        self.candidate=prepare_recipient(self.rfq,self.contact,organization_name='Synthetic supplier',
                                         evidence_reference=REFERENCE,now=NOW,halted=False)
        self.record=dict(version=1,candidate=self.candidate,recorded_at=self.candidate['recipient']['observed_at'],
                         state='DECLARED_RECIPIENT_DRAFT_ONLY',historical_only=True,**dict.fromkeys(_FLAGS_EXTRA,False))

    def test_preview_and_confirmed_save_exact_scope(self):
        self.action.return_value=self.candidate
        self.assertEqual(self.controller.preview(self.contact,'selected'),self.candidate)
        self.action.assert_called_once_with('recipient_preview',PLAN,draft_id=self.rfq['draft_id'],
            supplier=self.controller.supplier,recipient=self.contact,evidence_path='selected')
        self.action.reset_mock()
        with self.assertRaises(PermissionError):
            self.controller.save(self.contact,'selected',self.candidate,confirmed=1)
        self.action.assert_not_called()
        self.action.return_value=self.record
        self.assertEqual(self.controller.save(self.contact,'selected',self.candidate,confirmed=True),self.record)
        self.assertEqual(self.action.call_args.kwargs['expected_recipient_id'],self.candidate['recipient_id'])

    def test_history_rejects_duplicate_wrong_scope_and_authority(self):
        history=dict(scope=self.candidate['scope'],rows=[self.record],truncated=False,
                     historical_only=True,**dict.fromkeys(_FLAGS_EXTRA,False))
        self.action.return_value=history
        self.assertEqual(self.controller.history(),history)
        for changed in (dict(rows=[self.record,self.record]),dict(scope={}),dict(send_enabled=True),
                        dict(rows=[dict(self.record,mailbox_control_verified=0)])):
            self.action.return_value=dict(history,**changed)
            with self.assertRaises(ValueError):
                self.controller.history()

    def test_thread_none_creation_confirmation_and_forgery(self):
        self.action.return_value=None
        self.assertIsNone(self.controller.thread(self.record))
        self.action.reset_mock()
        with self.assertRaises(PermissionError):
            self.controller.thread(self.record,create=True,confirmed=False)
        self.action.assert_not_called()
        thread=open_thread(self.rfq,self.candidate,now=NOW,confirmed=True,halted=False)
        self.action.return_value=thread
        self.assertEqual(self.controller.thread(self.record,create=True,confirmed=True),thread)
        self.assertEqual(self.action.call_args.args[0],'thread_open')
        self.action.return_value=dict(thread,reply_authenticated=True)
        with self.assertRaises(ValueError):
            self.controller.thread(self.record)

    def test_halt_and_legacy_fail_closed(self):
        self.blocked=True
        with self.assertRaises(PermissionError):
            self.controller.history()
        self.action.assert_not_called()
        self.blocked=False
        with self.assertRaises(ValueError):
            CorrespondenceWorkspace(self.workspace,draft(pinned=False),fields())
        def halted(*args,**kwargs):
            self.blocked=True
            return self.candidate
        self.action.side_effect=halted
        with self.assertRaises(PermissionError):
            self.controller.preview(self.contact,'selected')

    def test_event_preview_and_exact_append(self):
        thread=open_thread(self.rfq,self.candidate,now=NOW,confirmed=True,halted=False)
        with TemporaryDirectory() as temp:
            path=Path(temp)/'reply.txt'
            path.write_bytes(b'owned simulated reply')
            self.action.return_value=thread
            expected=self.controller.preview_event(self.record,'SIMULATED_REPLY',path)
            self.assertEqual(expected,dict(thread_id=thread['thread_id'],head=thread['head_sha256'],
                kind='SIMULATED_REPLY',evidence=fingerprint(path,halted=False)))
            updated=append_event(self.rfq,self.candidate,thread,kind=expected['kind'],
                evidence_reference=expected['evidence'],expected_head=expected['head'],
                now=NOW,confirmed=True,halted=False)
            self.action.side_effect=[thread,updated]
            self.assertEqual(self.controller.save_event(self.record,path,expected,confirmed=True),updated)
            self.action.assert_called_with('thread_append',PLAN,draft_id=self.rfq['draft_id'],
                recipient_id=self.candidate['recipient_id'],supplier=self.controller.supplier,
                kind=expected['kind'],evidence_path=path,expected_head=expected['head'],
                expected_evidence=expected['evidence'],confirmed=True)

    def test_event_confirmation_stale_and_invalid_kind(self):
        thread=open_thread(self.rfq,self.candidate,now=NOW,confirmed=True,halted=False)
        expected=dict(thread_id=thread['thread_id'],head=thread['head_sha256'],
                      kind='SIMULATED_REPLY',evidence=REFERENCE)
        with self.assertRaises(PermissionError):
            self.controller.save_event(self.record,'unused',expected,confirmed=1)
        with self.assertRaises(ValueError):
            self.controller.preview_event(self.record,'SENT', 'unused')
        self.action.assert_not_called()
        self.action.return_value=thread
        with self.assertRaises(ValueError):
            self.controller.save_event(self.record,'unused',dict(expected,head='f'*64),confirmed=True)
        self.assertEqual(self.action.call_args.args[0],'thread_history')

    def test_event_response_forgery_and_replay(self):
        thread=open_thread(self.rfq,self.candidate,now=NOW,confirmed=True,halted=False)
        expected=dict(thread_id=thread['thread_id'],head=thread['head_sha256'],
                      kind='SIMULATED_REPLY',evidence=REFERENCE)
        wrong=append_event(self.rfq,self.candidate,thread,kind='LOCAL_FOLLOWUP_DRAFT',
            evidence_reference=REFERENCE,expected_head=expected['head'],now=NOW,confirmed=True,halted=False)
        self.action.side_effect=[thread,wrong]
        with self.assertRaises(ValueError):
            self.controller.save_event(self.record,'unused',expected,confirmed=True)
        self.action.side_effect=[wrong]
        with self.assertRaises(ValueError):
            self.controller.save_event(self.record,'unused',dict(expected,head=wrong['head_sha256']),confirmed=True)
        self.assertEqual(self.action.call_args.args[0],'thread_history')
