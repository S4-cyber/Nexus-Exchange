import copy
import unittest
from datetime import timedelta
from unittest.mock import Mock

import test_simulated_receivables as prior
from nexus_exchange.finance_workspace import FinanceWorkspace,aging,validate_record,record_text


class FinanceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=prior.SimulatedReceivablesTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.plan=self.fixture.plan
        self.issue=self.fixture.issue
        self.obligation=self.fixture.accept_note()
        self.busy=False
        self.workspace=FinanceWorkspace(self.obligation,action=self.guard.simulated_invoice_action,
            blocked_check=lambda:self.busy or self.guard.is_set())

    def create(self):
        self.workspace.preview(self.issue)
        return self.workspace.create(confirmed=True)

    def test_real_preview_create_partial_settlement_and_refresh(self):
        self.assertIsNone(self.workspace.refresh())
        initial=self.create()
        self.assertTrue(self.workspace.can_pay)
        part=self.workspace.payment("SIM-NATIVE1","75.13",self.issue,confirmed=True)
        self.assertEqual(part["simulated_outstanding_cents"],12487)
        final=self.workspace.payment("SIM-NATIVE2","124.87",self.issue,confirmed=True)
        self.assertFalse(self.workspace.can_pay)
        self.assertFalse(final["payment_received"])
        self.assertEqual(self.workspace.refresh(),final)
        self.assertIn("SIMULATION ONLY",record_text(final,self.workspace.projection(self.issue)))

    def test_as_of_excludes_future_receipts_and_preissue_face(self):
        record=self.create()
        due=record["invoice"]["due_date"]
        start=self.fixture.now.date()
        before=(start-timedelta(days=1)).isoformat()
        future=(start+timedelta(days=35)).isoformat()
        self.workspace.payment("SIM-NATIVE1","50",self.issue,confirmed=True)
        self.workspace.payment("SIM-NATIVE2","150",future,confirmed=True)
        early=self.workspace.projection(before)
        self.assertEqual(early["status"],"SIM_NOT_YET_ISSUED")
        self.assertEqual(early["simulated_outstanding_as_of_cents"],0)
        at_due=self.workspace.projection(due)
        self.assertEqual(at_due["status"],"SIM_DUE_TODAY")
        self.assertEqual(at_due["future_dated_receipts_cents"],15000)
        self.assertEqual(at_due["simulated_overdue_cents"],0)
        late=self.workspace.projection((start+timedelta(days=31)).isoformat())
        self.assertEqual(late["days_overdue"],1)
        self.assertEqual(late["simulated_overdue_cents"],15000)
        final=self.workspace.projection(future)
        self.assertEqual(final["status"],"SIM_SETTLED_AS_OF")
        self.assertEqual(final["future_dated_receipts_cents"],0)
        self.assertFalse(final["funds_available"])

    def test_confirmation_and_busy_clear(self):
        with self.assertRaises(PermissionError):
            self.workspace.create(confirmed=True)
        self.workspace.preview(self.issue)
        with self.assertRaises(PermissionError):
            self.workspace.create(confirmed=1)
        self.busy=True
        with self.assertRaises(PermissionError):
            self.workspace.create(confirmed=True)
        self.assertIsNone(self.workspace.previewed)
        self.assertFalse(self.fixture.path.exists())

    def test_stale_head_and_failed_mutation_clear_record(self):
        record=self.create()
        self.fixture.payment(record,ref="SIM-OTHER")
        with self.assertRaises(ValueError):
            self.workspace.payment("SIM-NATIVE1","1",self.issue,confirmed=True)
        self.assertIsNone(self.workspace.record)
        self.assertEqual(self.workspace.refresh()["simulated_received_cents"],5000)

    def test_changed_evidence_historical_only(self):
        record=self.create()
        self.fixture.fixture.evidence.write_bytes(b"new revision request")
        revised=self.fixture.fixture.note(self.obligation,kind="revision_request_noted")
        new=FinanceWorkspace(revised,action=self.guard.simulated_invoice_action,blocked_check=self.guard.is_set)
        self.assertEqual(new.refresh(),record)
        self.assertFalse(new.can_pay)
        self.assertTrue(new.projection(self.issue)["evidence_changed"])
        with self.assertRaises(PermissionError):
            new.payment("SIM-HOLD","1",self.issue,confirmed=True)
        with self.assertRaises(ValueError):
            self.workspace.payment("SIM-STALE","1",self.issue,confirmed=True)

    def test_tampered_totals_chain_and_authority_rejected(self):
        self.create()
        record=self.workspace.payment("SIM-NATIVE1","20",self.issue,confirmed=True)
        corrupted=copy.deepcopy(record)
        corrupted["receipts"][0]["amount_cents"]=1
        for raw in (dict(record,simulated_outstanding_cents=1),dict(record,funds_available=True),
                    dict(record,head_sha256="0"*64),corrupted):
            with self.assertRaises(ValueError):
                validate_record(raw,self.plan,self.obligation)

    def test_preview_scope_validation(self):
        invoice=self.fixture.preview()
        altered=dict(invoice)
        from nexus_exchange.lead_store import _digest,_json
        altered["obligation_id"]="0"*64
        altered["invoice_id"]=_digest(_json({k:v for k,v in altered.items() if k!="invoice_id"}))
        workspace=FinanceWorkspace(self.obligation,action=Mock(return_value=altered),blocked_check=lambda:False)
        with self.assertRaises(ValueError):
            workspace.preview(self.issue)
        self.assertIsNone(workspace.previewed)

    def test_wrong_obligation_cannot_relabel_saved_invoice(self):
        record=self.create()
        other=copy.deepcopy(self.obligation)
        # Another valid artifact for the same plan has a different source
        # contract; validate against real stored record, not a forged scope.
        source=self.fixture.fixture.source
        source.write_bytes(b"name,id,category\nGamma,001,Design\nBeta,002,Research\n")
        args=dict(source_path=source,columns=["id","name","category"],key_column="id",expected_rows=2)
        preview=self.guard.csv_file_action("preview",self.plan,confirmed=True,**args)
        from nexus_exchange.deliverable_files import preview_pins
        artifact=self.fixture.fixture.directory/"different.csv"
        self.guard.csv_file_action("export",self.plan,confirmed=True,destination_path=artifact,
            **args,**preview_pins(preview))
        other=self.guard.csv_file_action("register",self.plan,confirmed=True,artifact_path=artifact,
            **args,**preview_pins(preview))
        workspace=FinanceWorkspace(other,action=self.guard.simulated_invoice_action,blocked_check=self.guard.is_set)
        with self.assertRaises(ValueError):
            workspace.refresh()
        self.assertEqual(self.workspace.record,record)

    def test_post_call_halt_withholds_result(self):
        record=self.create()
        states=iter([False,True])
        workspace=FinanceWorkspace(self.obligation,action=Mock(return_value=record),
            blocked_check=lambda:next(states,True))
        with self.assertRaises(PermissionError):
            workspace.refresh()
        self.assertIsNone(workspace.record)

    def test_invalid_as_of_and_defensive_copy(self):
        record=self.create()
        for day in ("bad","2026-02-30",None):
            with self.assertRaises(ValueError):
                self.workspace.projection(day)
        copy_of=self.workspace.record
        copy_of["invoice"]["gross_cents"]=1
        self.assertEqual(self.workspace.record,record)
        self.assertFalse(self.workspace.projection(self.issue)["actual_balance_verified"])


if __name__=="__main__":
    unittest.main()
