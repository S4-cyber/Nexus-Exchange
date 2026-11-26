import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_evidence import ScenarioEvidenceStore
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.council_workspace import (CouncilWorkspace, snapshot_text, ledger_text, audit_text,
    validate_advisory_completion)
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam


class CouncilWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.now=NOW
        self.declared=profile()
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:self.now)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.declared,halted=False)
        with ScenarioEvidenceStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(self.report,now=self.now,halted=False)
            lead=store.browse(now=self.now,profile=self.declared,source="sam",halted=False)["leads"][0]
            self.key=store.save(context_for(lead),scenario(),plan(),profile=self.declared,
                                now=self.now,halted=False)
        self.guard=RuntimeGuard(self.directory,clock=lambda:self.now)
        self.addCleanup(self.guard.close)
        self.guard.resume()
        self.busy=False
        self.action=Mock(side_effect=self.guard.council_action)
        self.workspace=CouncilWorkspace(self.key,action=self.action,
                                        blocked_check=lambda:self.busy or self.guard.is_set())

    def test_open_and_inspect_never_register_or_consume_attempt(self):
        self.action.assert_not_called()
        snap=self.workspace.inspect()
        self.action.assert_called_once_with("inspect",self.key)
        self.assertFalse((self.directory/"council.sqlite3").exists())
        self.assertIn("UNVERIFIED LOCAL REVIEW",snapshot_text(snap))
        self.assertIn("0/17",snapshot_text(snap))

    def test_explicit_register_review_and_historical_display(self):
        registered=self.workspace.register()
        self.assertEqual(registered["attempts_used"],0)
        self.assertIn("0/3",ledger_text(registered))
        result=self.workspace.run_once()
        self.assertEqual(result["ledger"]["attempts_used"],1)
        history=self.workspace.history()
        self.assertEqual(history["attempts_used"],1)
        row=history["attempts"][0]
        self.assertIn("HISTORICAL ONLY",audit_text(row))
        self.assertIn(row["audit"]["snapshot"]["snapshot_sha256"],audit_text(row))
        self.assertIn("NEEDS_EVIDENCE",audit_text(row))
        self.assertIn("No current decision",audit_text(row))
        self.assertEqual([call.args[0] for call in self.action.call_args_list],
                         ["register","run_once","history"])

    def test_missing_registration_cannot_implicitly_register(self):
        with self.assertRaises(ValueError):
            self.workspace.run_once()
        self.action.assert_called_once_with("run_once",self.key)
        with self.assertRaises(ValueError):
            self.workspace.history()

    def test_halt_and_busy_gate_precede_facade_calls(self):
        self.busy=True
        for operation in (self.workspace.inspect,self.workspace.register,self.workspace.run_once,self.workspace.history):
            with self.assertRaises(PermissionError):
                operation()
        self.action.assert_not_called()
        self.busy=False
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.workspace.inspect()
        self.action.assert_not_called()
        self.guard.resume()
        self.assertEqual(self.workspace.inspect()["plan_id"],self.key)

    def test_unknown_blocked_state_and_bad_plan_are_rejected(self):
        for value in (None,0,True):
            action=Mock()
            workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:value)
            with self.assertRaises(PermissionError):
                workspace.inspect()
            action.assert_not_called()
        for key in (None,"a"*63,"é"*64):
            with self.assertRaises(ValueError):
                CouncilWorkspace(key,action=self.action,blocked_check=lambda:False)

    def test_historical_review_remains_distinct_after_profile_change(self):
        self.workspace.register()
        self.workspace.run_once()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.workspace.inspect()
        history=self.workspace.history()
        self.assertFalse(history["current_decision"])
        self.assertIn("HISTORICAL ONLY",audit_text(history["attempts"][0]))

    def test_third_review_is_terminal_and_history_remains_available(self):
        self.workspace.register()
        for _ in range(3):
            result=self.workspace.run_once()
        self.assertEqual(result["ledger"]["state"],"ESCALATE")
        self.assertIn("No next attempt",ledger_text(result["ledger"]))
        with self.assertRaises(PermissionError):
            self.workspace.run_once()
        self.assertEqual(self.workspace.history()["attempts_used"],3)

    def test_legacy_and_interrupted_rows_never_fabricate_snapshot(self):
        for state,label in (("LEGACY_DIGEST_ONLY","Legacy digest only"),
                            ("RESERVED_NO_REPORT","Reserved; no report"),
                            ("INTERRUPTED_NO_REPORT","Interrupted; no report")):
            row=dict(attempt=1,outcome=None,reserved_at=NOW.isoformat(),
                     completed_at=None,report_sha256=None,audit_sha256=None,
                     reservation_id="a"*64,audit_state=state,audit=None)
            text=audit_text(row)
            self.assertIn(label,text)
            self.assertIn("No current decision",text)
            self.assertNotIn("Modeled expected net",text)

    def test_scope_and_authority_mismatch_rejected(self):
        snap=self.workspace.inspect()
        action=Mock(return_value=dict(snap,external_authority=True))
        workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:False)
        with self.assertRaises(ValueError):
            workspace.inspect()
        action.return_value=dict(snap,plan_id="a"*64)
        with self.assertRaises(ValueError):
            workspace.inspect()

    def test_result_withheld_if_runtime_becomes_blocked(self):
        snap=self.workspace.inspect()
        states=iter([False,True])
        workspace=CouncilWorkspace(self.key,action=Mock(return_value=snap),
                                    blocked_check=lambda:next(states))
        with self.assertRaises(PermissionError):
            workspace.inspect()

    def test_context_layers_do_not_consume_attempts_or_authorize(self):
        from nexus_exchange.context_packet import validate_packet
        for level in ("summary","review","evidence"):
            packet,snap=self.workspace.context(level)
            self.assertEqual(packet,validate_packet(packet,snap,halted=False))
            self.assertEqual(packet["plan_id"],self.key)
            self.assertFalse(packet["external_authority"])
        self.assertFalse((self.directory/"council.sqlite3").exists())
        self.assertEqual([call.args[0] for call in self.action.call_args_list],["inspect"]*3)
        self.workspace.register()
        self.workspace.context("review")
        self.assertEqual(self.workspace.history()["attempts_used"],0)
        self.busy=True
        with self.assertRaises(PermissionError):
            self.workspace.context("summary")

    def test_advisory_budget_is_read_only_and_plan_scoped(self):
        budget=self.workspace.advisory_status()
        self.assertEqual((budget["state"],budget["attempts_used"],budget["next_attempt"]),
                         ("NOT_STARTED",0,1))
        self.assertFalse(budget["dispatch_enabled"])
        self.assertFalse((self.directory/"local-advisory.sqlite3").exists())
        self.assertFalse((self.directory/"council.sqlite3").exists())
        self.action.assert_called_once_with("advisory_status",self.key)
        self.busy=True
        with self.assertRaises(PermissionError):
            self.workspace.advisory_status()
        self.action.assert_called_once_with("advisory_status",self.key)
        self.busy=False
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.workspace.advisory_status()

    def test_advisory_budget_rejects_false_authority_and_bad_transitions(self):
        budget=self.workspace.advisory_status()
        action=Mock()
        workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:False)
        for change in (dict(dispatch_enabled=True),dict(plan_id="a"*64),
                       dict(next_attempt=True),dict(attempts_used=False),
                       dict(state="REVIEWED",attempts_used=0,next_attempt=None),
                       dict(state="FAILED",attempts_used=3,next_attempt=4),
                       dict(historical_only=False)):
            with self.subTest(change=change):
                action.return_value=dict(budget,**change)
                with self.assertRaises(ValueError):
                    workspace.advisory_status()

    def test_synthetic_advisory_decline_and_truthy_consent_never_start(self):
        preview=self.guard.prepare_advisory_process(self.key)
        action=Mock(return_value=preview)
        workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:False)
        for consent in (False,None,1,"yes"):
            action.reset_mock()
            self.assertIsNone(workspace.launch_advisory(lambda value:consent))
            action.assert_called_once_with("advisory_prepare",self.key)
        self.assertFalse((self.directory/"local-advisory.sqlite3").exists())

    def test_synthetic_advisory_validates_preview_before_confirmation(self):
        preview=self.guard.prepare_advisory_process(self.key)
        action=Mock()
        confirm=Mock(return_value=True)
        workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:False)
        for change in (dict(external_authority=True),dict(dispatch_enabled=True),
                       dict(synthetic_only=1),dict(next_attempt=True),
                       dict(plan_id="a"*64),dict(preview_id="not-a-token"),
                       dict(snapshot_sha256="bad")):
            action.return_value=dict(preview,**change)
            with self.assertRaises(ValueError):
                workspace.launch_advisory(confirm)
        confirm.assert_not_called()

    def test_synthetic_advisory_rechecks_busy_and_binds_exact_preview(self):
        preview=self.guard.prepare_advisory_process(self.key)
        action=Mock(side_effect=[preview,{"attempt":1}])
        workspace=CouncilWorkspace(self.key,action=action,blocked_check=lambda:self.busy)
        def blocked(value):
            self.busy=True
            return True
        with self.assertRaises(PermissionError):
            workspace.launch_advisory(blocked)
        action.assert_called_once_with("advisory_prepare",self.key)
        self.busy=False
        action.reset_mock()
        action.side_effect=[preview,{"attempt":1}]
        self.assertEqual(workspace.launch_advisory(lambda value:True),{"attempt":1})
        action.assert_called_with("advisory_start",self.key,
                                  preview_id=preview["preview_id"],confirmed=True)


    def test_advisory_completion_display_is_bound_to_reservation(self):
        from nexus_exchange.local_advisory import _digest
        from copy import deepcopy
        flags=dict(independently_verified=False,execution_eligible=False,
                   external_authority=False,dispatch_enabled=False)
        ticket=dict(plan_id=self.key,attempt=1,reservation_id="a"*64,
                    request_sha256="b"*64,external_authority=False)
        review=dict(format="nexus-local-advice-review-v1",request_sha256="b"*64,
                    response_sha256="c"*64,model_sha256="d"*64,**flags)
        row=dict(attempt=1,state="REVIEWED",reservation_id="a"*64,
                 request_sha256="b"*64,response_sha256="c"*64,
                 model_sha256="d"*64,review_sha256=_digest(review))
        report=dict(plan_id=self.key,state="REVIEWED",historical_only=True,
                    durable_retry_enforced=True,next_attempt=None,attempts_used=1,
                    attempts=[row],review=review,**flags)
        self.assertIs(validate_advisory_completion(report,ticket),report)
        for target,key,value in (
                ("report","plan_id","e"*64),("report","attempts_used",True),
                ("report","next_attempt",2),("report","external_authority",True),
                ("row","reservation_id","f"*64),("row","review_sha256","f"*64),
                ("review","dispatch_enabled",True),("review","response_sha256","f"*64)):
            with self.subTest(target=target,key=key):
                changed=deepcopy(report)
                selected={"report":changed,"row":changed["attempts"][0],
                          "review":changed["review"]}[target]
                selected[key]=value
                with self.assertRaises(ValueError):
                    validate_advisory_completion(changed,ticket)
