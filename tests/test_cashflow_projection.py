import unittest
from datetime import timedelta
from unittest.mock import patch, Mock

import test_simulated_receivables as prior
from test_cash_feasibility import scenario
from nexus_exchange.cash_feasibility import COSTS
from nexus_exchange.finance_workspace import FinanceWorkspace
from nexus_exchange.cashflow_projection import (
    project_cashflow, validate_projection, projection_text,
)
from nexus_exchange.scenario_store import ScenarioStore


class CashflowTests(unittest.TestCase):
    def setup_model(self,**changes):
        costs=dict.fromkeys(COSTS,"0.00")
        costs.update(changes)
        fixture=prior.SimulatedReceivablesTests()
        with patch("test_digital_deliverable.scenario",return_value=scenario(costs=costs)):
            fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        obligation=fixture.accept_note()
        workspace=FinanceWorkspace(obligation,action=fixture.guard.simulated_invoice_action,
                                   blocked_check=fixture.guard.is_set)
        workspace.preview(fixture.issue)
        workspace.create(confirmed=True)
        return fixture,workspace

    def settle(self,fixture,workspace):
        return workspace.payment("SIM-FULL","200",fixture.issue,confirmed=True)

    def test_real_cost_adjusted_settlement_and_rounded_reserve(self):
        f,w=self.setup_model(platform_fees="12.34",software="20",taxes="5.66")
        record=self.settle(f,w)
        result=w.cashflow(f.issue,"3333")
        self.assertEqual(result["modeled_total_cost_cents"],3800)
        self.assertEqual(result["modeled_full_collection_net_cents"],16200)
        self.assertEqual(result["modeled_net_as_of_cents"],16200)
        self.assertEqual(result["modeled_protected_reserve_cents"],5400)
        self.assertEqual(result["modeled_reinvestment_cents"],10800)
        self.assertTrue(result["allocation_modeled"])
        self.assertFalse(result["funds_available"])
        self.assertFalse(result["reinvestment_authorized"])
        self.assertIn("Hypothetical reinvestment",projection_text(result))
        self.assertEqual(w.record,record)
        self.assertEqual(w.cashflow(f.issue,"3333"),result)

    def test_unknown_costs_never_assumed_zero(self):
        f,w=self.setup_model(software=None,taxes="1.25")
        self.settle(f,w)
        result=w.cashflow(f.issue,"5000")
        self.assertEqual(result["unknown_cost_categories"],["software"])
        self.assertEqual(result["known_cost_subtotal_cents"],125)
        for key in ("modeled_total_cost_cents","modeled_net_as_of_cents",
                    "modeled_full_collection_net_cents","modeled_protected_reserve_cents",
                    "modeled_reinvestment_cents"):
            self.assertIsNone(result[key])
        self.assertIn("MODELED_COSTS_UNKNOWN",result["reasons"])
        self.assertFalse(result["allocation_modeled"])

    def test_negative_surplus_holds_allocation(self):
        f,w=self.setup_model(subcontracting="250.00")
        self.settle(f,w)
        result=w.cashflow(f.issue,"5000")
        self.assertEqual(result["modeled_net_as_of_cents"],-5000)
        self.assertEqual(result["modeled_cost_shortfall_cents"],5000)
        self.assertFalse(result["allocation_modeled"])
        self.assertIsNone(result["modeled_reinvestment_cents"])

    def test_partial_and_future_receipts_do_not_allocate(self):
        f,w=self.setup_model(software="25.00")
        day=(f.now.date()+timedelta(days=40)).isoformat()
        w.payment("SIM-PARTIAL","50",f.issue,confirmed=True)
        w.payment("SIM-FUTURE","150",day,confirmed=True)
        result=w.cashflow(f.issue,"5000")
        self.assertEqual(result["modeled_net_as_of_cents"],2500)
        self.assertEqual(result["future_dated_receipts_cents"],15000)
        self.assertFalse(result["allocation_modeled"])
        self.assertIn("MODEL_NOT_FULLY_SETTLED_AS_OF",result["reasons"])
        self.assertTrue(w.cashflow(day,"5000")["allocation_modeled"])

    def test_preissue_cost_timing_remains_unresolved(self):
        f,w=self.setup_model(materials="10")
        self.settle(f,w)
        before=(f.now.date()-timedelta(days=1)).isoformat()
        result=w.cashflow(before,"10000")
        self.assertEqual(result["modeled_total_cost_cents"],1000)
        self.assertIsNone(result["modeled_net_as_of_cents"])
        self.assertIsNone(result["modeled_cost_shortfall_cents"])
        self.assertIn("PREISSUE_COST_TIMING_UNRESOLVED",result["reasons"])

    def test_reserve_extremes_and_exact_cent_ceiling(self):
        f,w=self.setup_model(software="199.99")
        self.settle(f,w)
        for bps,reserve,reinvest in (("0",0,1),("1",1,0),("10000",1,0)):
            result=w.cashflow(f.issue,bps)
            self.assertEqual((result["modeled_protected_reserve_cents"],
                              result["modeled_reinvestment_cents"]),(reserve,reinvest))
        for invalid in ("","10001","-1","1.5",True,"2e3"):
            with self.assertRaises(ValueError):
                w.cashflow(f.issue,invalid)

    def test_evidence_change_holds_even_settled_simulation(self):
        f,w=self.setup_model()
        self.settle(f,w)
        f.fixture.evidence.write_bytes(b"synthetic later revision")
        revised=f.fixture.note(f.obligation,kind="revision_request_noted")
        with self.assertRaises(ValueError):
            w.cashflow(f.issue,"5000")
        self.assertIsNone(w.record)
        current=FinanceWorkspace(revised,action=f.guard.simulated_invoice_action,blocked_check=f.guard.is_set)
        current.refresh()
        result=current.cashflow(f.issue,"5000")
        self.assertIn("OBLIGATION_EVIDENCE_CHANGED",result["reasons"])
        self.assertFalse(result["allocation_modeled"])

    def test_stale_receipt_head_and_halt(self):
        f,w=self.setup_model()
        f.payment(w.record,ref="SIM-OTHER")
        with self.assertRaises(ValueError):
            w.cashflow(f.issue,"5000")
        self.assertIsNone(w.record)
        w.refresh()
        f.guard.set()
        with self.assertRaises(PermissionError):
            w.cashflow(f.issue,"5000")

    def test_saved_plan_cost_tampering_and_projection_tampering(self):
        f,w=self.setup_model()
        record=self.settle(f,w)
        with ScenarioStore(f.fixture.directory/"scout-leads.sqlite3") as store:
            saved=store.get(f.plan,halted=False)
        saved["scenario"]["costs"]["software"]="1.00"
        with self.assertRaises(ValueError):
            project_cashflow(record,w.obligation,saved,as_of=f.issue,reserve_bps=5000,halted=False)
        result=w.cashflow(f.issue,"5000")
        for bad in (dict(result,modeled_reinvestment_cents=1),dict(result,funds_available=True),
                    dict(result,projection_sha256="0"*64)):
            with self.assertRaises(ValueError):
                validate_projection(bad,record,w.obligation,as_of=f.issue,reserve_bps=5000)

    def test_post_call_halt_withholds_projection(self):
        f,w=self.setup_model()
        record=self.settle(f,w)
        result=w.cashflow(f.issue,"5000")
        w.action=Mock(return_value=result)
        states=iter([False,True])
        w.blocked_check=lambda:next(states,True)
        with self.assertRaises(PermissionError):
            w.cashflow(f.issue,"5000")
        self.assertIsNone(w.record)


if __name__=="__main__":
    unittest.main()
