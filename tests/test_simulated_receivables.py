import copy
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_deliverable_obligations as prior
from nexus_exchange.simulated_receivables import InvoiceStore,build_invoice,MAX_RECEIPTS
from nexus_exchange.scenario_store import ScenarioStore
from nexus_exchange.owner_profile import ProfileStore
from test_owner_profile import profile


class SimulatedReceivablesTests(unittest.TestCase):
    def setUp(self):
        self.fixture=prior.ObligationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.plan=self.fixture.plan
        self.path=self.fixture.directory/"operator-simulated-invoices.sqlite3"
        self.now=self.fixture.fixture.fixture.now
        self.issue=self.now.date().isoformat()
        self.obligation=self.fixture.register()

    def accept_note(self):
        self.obligation=self.fixture.note(self.obligation)
        return self.obligation

    def preview(self,**changes):
        args=dict(obligation_id=self.obligation["obligation_id"],
                  expected_obligation_head=self.obligation["head_sha256"],issue_date=self.issue)
        args.update(changes)
        return self.guard.simulated_invoice_action("preview",self.plan,**args)

    def create(self,invoice=None,**changes):
        if invoice is None:
            invoice=self.preview()
        args=dict(obligation_id=self.obligation["obligation_id"],
                  expected_obligation_head=self.obligation["head_sha256"],issue_date=invoice["issue_date"],
                  expected_invoice_id=invoice["invoice_id"],confirmed=True)
        args.update(changes)
        return self.guard.simulated_invoice_action("create",self.plan,**args)

    def payment(self,record,amount="50.00",ref="SIM-FIRST",**changes):
        args=dict(invoice_id=record["invoice"]["invoice_id"],expected_head=record["head_sha256"],
                  sim_reference=ref,amount=amount,paid_on=self.issue,confirmed=True)
        args.update(changes)
        return self.guard.simulated_invoice_action("payment",self.plan,**args)

    def history(self,record):
        return self.guard.simulated_invoice_action("history",self.plan,invoice_id=record["invoice"]["invoice_id"])

    def test_requires_acceptance_claim_but_never_verifies_buyer(self):
        with self.assertRaises(ValueError):
            self.preview()
        self.assertFalse(self.path.exists())
        self.accept_note()
        invoice=self.preview()
        self.assertEqual(invoice["gross_cents"],20000)
        self.assertEqual(invoice["payment_days"],30)
        self.assertEqual(invoice["due_date"],(self.now.date()+timedelta(days=30)).isoformat())
        self.assertEqual(invoice["mode"],"SIMULATION_ONLY")
        for flag in ("buyer_accepted","invoice_issued","invoice_eligible","real_receivable",
                     "payment_received","revenue_realized","funds_available","external_authority"):
            self.assertIs(invoice[flag],False)
        self.assertFalse(self.path.exists())

    def test_create_idempotent_and_exact_plan_history(self):
        self.accept_note()
        invoice=self.preview()
        self.assertIsNone(self.guard.simulated_invoice_action("find",self.plan))
        record=self.create(invoice)
        self.assertEqual(record,self.create(invoice))
        self.assertEqual(record,self.history(record))
        self.assertEqual(record,self.guard.simulated_invoice_action("find",self.plan))
        self.assertEqual(record["simulated_outstanding_cents"],20000)
        self.assertEqual(record["state"],"SIMULATED_UNPAID")
        with self.assertRaises(ValueError):
            self.guard.simulated_invoice_action("history","0"*64,invoice_id=invoice["invoice_id"])

    def test_exact_partial_and_settled_balances(self):
        self.accept_note()
        record=self.create()
        partial=self.payment(record,"75.13")
        self.assertEqual(partial["simulated_received_cents"],7513)
        self.assertEqual(partial["simulated_outstanding_cents"],12487)
        self.assertEqual(partial["state"],"SIMULATED_PARTIAL")
        final=self.payment(partial,"124.87","SIM-SECOND")
        self.assertEqual(final["simulated_received_cents"],20000)
        self.assertEqual(final["simulated_outstanding_cents"],0)
        self.assertEqual(final["state"],"SIMULATED_SETTLED")
        self.assertFalse(final["payment_received"])
        self.assertFalse(final["revenue_realized"])
        self.assertEqual(self.history(final),final)

    def test_duplicate_overpayment_stale_head_and_settled_reject(self):
        self.accept_note()
        record=self.create()
        partial=self.payment(record)
        for args in (dict(record=partial,ref="SIM-FIRST"),dict(record=partial,amount="150.01",ref="SIM-OVER"),
                     dict(record=record,ref="SIM-STALE")):
            with self.assertRaises(ValueError):
                self.payment(**args)
        self.assertEqual(self.history(record),partial)
        final=self.payment(partial,"150","SIM-SECOND")
        with self.assertRaises(ValueError):
            self.payment(final,"0.01","SIM-EXTRA")
        self.assertEqual(self.history(final),final)

    def test_changed_obligation_holds_new_simulation_and_receipts(self):
        self.accept_note()
        invoice=self.preview()
        record=self.create(invoice)
        self.fixture.evidence.write_bytes(b"synthetic revised requirements")
        self.fixture.note(self.obligation,kind="revision_request_noted")
        with self.assertRaises(ValueError):
            self.preview()
        with self.assertRaises(ValueError):
            self.payment(record)
        self.assertEqual(self.history(record),record)

    def test_confirmed_preview_identity_and_one_invoice_per_plan(self):
        self.accept_note()
        invoice=self.preview()
        for changes in (dict(confirmed=1),dict(expected_invoice_id="0"*64)):
            with self.assertRaises((ValueError,PermissionError)):
                self.create(invoice,**changes)
        self.assertFalse(self.path.exists())
        self.create(invoice)
        alternate=self.preview(issue_date=(self.now.date()+timedelta(days=1)).isoformat())
        with self.assertRaises(ValueError):
            self.create(alternate)

    def test_amount_date_and_reference_validation(self):
        self.accept_note()
        record=self.create()
        for amount in ("0","-1","0.001","1e2",True,"1000000000000"):
            with self.assertRaises(ValueError):
                self.payment(record,amount)
        for ref in ("REAL-123","SIM-","SIM-secret@email","SIM-lower"):
            with self.assertRaises(ValueError):
                self.payment(record,ref=ref)
        with self.assertRaises(ValueError):
            self.payment(record,paid_on=(self.now.date()-timedelta(days=1)).isoformat())
        with self.assertRaises(ValueError):
            self.preview(issue_date="2026-02-30")
        self.assertEqual(self.history(record),record)

    def test_historical_simulation_does_not_reinstate_current_eligibility(self):
        self.accept_note()
        with ProfileStore(self.fixture.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        record=self.create()
        self.assertTrue(record["historical_only"])
        self.assertFalse(record["execution_eligible"])
        self.assertFalse(record["zero_capital_verified"])

    def test_reconciliation_integrity_and_rollback_on_halt(self):
        self.accept_note()
        record=self.create()
        with InvoiceStore(self.path,existing_only=True) as store:
            states=iter([False,False,True])
            with self.assertRaises(PermissionError):
                store.payment(self.plan,record["invoice"]["invoice_id"],expected_head=record["head_sha256"],
                    sim_reference="SIM-ROLLBACK",amount="1",paid_on=self.issue,now=self.now,
                    confirmed=True,halted=False,halt_check=lambda:next(states,True))
        self.assertEqual(self.history(record),record)
        self.payment(record)
        with InvoiceStore(self.path,existing_only=True) as store:
            store.db.execute("UPDATE sim_receipts_v1 SET payload='{}'")
        with self.assertRaises(ValueError):
            self.history(record)

    def test_synthetic_reference_unique_across_invoice_records(self):
        self.accept_note()
        invoice=self.preview()
        # Store-level fixture for an independent alternative plan; no real
        # customer data. Recompute the synthetic invoice identity only.
        from nexus_exchange.lead_store import _digest,_json
        alternate=dict(invoice,plan_id="1"*64,obligation_id="2"*64)
        alternate["invoice_id"]=_digest(_json({k:v for k,v in alternate.items() if k!="invoice_id"}))
        with InvoiceStore(":memory:") as store:
            a=store.create(invoice,now=self.now,confirmed=True,halted=False)
            b=store.create(alternate,now=self.now,confirmed=True,halted=False)
            for i,row in enumerate((a,b)):
                args=dict(expected_head=row["head_sha256"],sim_reference="SIM-GLOBAL",amount="1",
                          paid_on=self.issue,now=self.now,confirmed=True,halted=False)
                key=row["invoice"]["invoice_id"]
                plan=row["invoice"]["plan_id"]
                if i==0:
                    store.payment(plan,key,**args)
                else:
                    with self.assertRaises(ValueError):
                        store.payment(plan,key,**args)

    def test_suppressed_receipt_never_reports_success(self):
        self.accept_note()
        original=self.create()
        with InvoiceStore(self.path,existing_only=True) as store:
            store.db.execute("CREATE TRIGGER suppressed BEFORE INSERT ON sim_receipts_v1 "
                             "BEGIN SELECT RAISE(IGNORE); END")
            with self.assertRaisesRegex(ValueError,"trigger"):
                self.payment(original)
            # Independently exercise the publication check on the same connection,
            # even if the preventative guard is unavailable. Synthetic test only.
            with patch.object(store,"_guard_write",return_value=None):
                with self.assertRaisesRegex(ValueError,"publication mismatch"):
                    store.payment(self.plan,original["invoice"]["invoice_id"],
                        expected_head=original["head_sha256"],sim_reference="SIM-FIRST",
                        amount="50.00",paid_on=self.issue,now=self.now,confirmed=True,halted=False)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(self.history(original),original)
            store.db.execute("DROP TRIGGER suppressed")
        self.assertEqual(self.payment(original)["simulated_received_cents"],5000)

    def test_temporary_shadow_and_trigger_do_not_capture_receipts(self):
        self.accept_note()
        original=self.create()
        with InvoiceStore(self.path,existing_only=True) as store:
            args=dict(expected_head=original["head_sha256"],sim_reference="SIM-TEMP",
                      amount="1",paid_on=self.issue,now=self.now,confirmed=True,halted=False)
            key=original["invoice"]["invoice_id"]
            store.db.execute("CREATE TEMP TABLE sim_receipts_v1 AS SELECT * FROM main.sim_receipts_v1")
            self.assertEqual(store.history(self.plan,key,now=self.now,halted=False),original)
            with self.assertRaisesRegex(ValueError,"shadow"):
                store.payment(self.plan,key,**args)
            store.db.execute("DROP TABLE temp.sim_receipts_v1")
            store.db.execute("CREATE TEMP TRIGGER suppressed BEFORE INSERT ON main.sim_receipts_v1 "
                             "BEGIN SELECT RAISE(IGNORE); END")
            with self.assertRaisesRegex(ValueError,"trigger"):
                store.payment(self.plan,key,**args)
            store.db.execute("DROP TRIGGER temp.suppressed")
            self.assertEqual(store.history(self.plan,key,now=self.now,halted=False),original)
            self.assertEqual(store.payment(self.plan,key,**args)["simulated_received_cents"],100)

    def test_halt_unknown_action_and_capacity(self):
        self.accept_note()
        record=self.create()
        with patch("nexus_exchange.simulated_receivables.MAX_RECEIPTS",0):
            with self.assertRaises(ValueError):
                self.payment(record)
        with self.assertRaises(ValueError):
            self.guard.simulated_invoice_action("send",self.plan)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.history(record)
        with self.assertRaises(PermissionError):
            self.payment(record)


if __name__=="__main__":
    unittest.main()
