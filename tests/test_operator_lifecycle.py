"""One shared synthetic plan, from Scout/Council through local collection simulation.

The RFQ/thread and service artifact are independently scoped to the same plan;
this is not evidence that a supplier reply creates a buyer obligation.
"""
import unittest

import test_operator_scenario_integration as prior
import test_digital_deliverable as digital
from nexus_exchange.csv_workspace import CsvWorkspace
from nexus_exchange.evidence import fingerprint
from nexus_exchange.governor import Action, decide


class OperatorLifecycleTests(unittest.TestCase):
    def test_shared_plan_correspondence_work_and_simulated_collection(self):
        f=prior.OperatorRuntimeTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        guard=f.guard
        plan=f.key
        guard.resume()
        current=guard.council_action("inspect",plan)
        draft=f.call()["draft"]
        self.assertEqual(draft["request"]["plan_id"],plan)
        self.assertEqual(draft["request"]["observation_sha256"],current["context"]["observation_sha256"])
        key=draft["draft_id"]
        supplier=f.supplier()
        ack=guard.operator_action("acknowledge",plan,draft_id=key,supplier=supplier,confirmed=True)
        self.assertEqual(ack["state"],"LOCALLY_ACKNOWLEDGED_DRAFT_ONLY")
        path=f.directory/"synthetic-contact.txt"
        path.write_bytes(b"owned synthetic contact fixture")
        recipient=dict(scheme="REGISTRY",identifier="SYNTHETIC-1",
            organization_name="Synthetic supplier",email="quotes@example.org",
            source_url="https://example.org/contact",observed_at=f.now.isoformat())
        args=dict(draft_id=key,supplier=supplier,recipient=recipient,evidence_path=path)
        candidate=guard.operator_action("recipient_preview",plan,**args)
        guard.operator_action("recipient_save",plan,**args,
            expected_recipient_id=candidate["recipient_id"],confirmed=True)
        scope=dict(draft_id=key,recipient_id=candidate["recipient_id"])
        opened=guard.operator_action("thread_open",plan,**scope,supplier=supplier,confirmed=True)
        path.write_bytes(b"owned synthetic supplier response; no authenticated quote")
        thread=guard.operator_action("thread_append",plan,**scope,supplier=supplier,
            kind="SIMULATED_REPLY",evidence_path=path,expected_head=opened["head_sha256"],
            expected_evidence=fingerprint(path,halted=False),confirmed=True)
        self.assertFalse(thread["reply_authenticated"])
        self.assertFalse(thread["delivery_verified"])
        self.assertFalse(thread["send_enabled"])

        source=f.directory/"owned.csv"
        source.write_bytes(digital.RAW)
        target=f.directory/"local-output.csv"
        work=CsvWorkspace(plan,action=guard.csv_file_action,blocked_check=guard.is_set)
        preview=work.preview(source,"id,name,category","id","2")
        self.assertEqual(preview["artifact"],digital.EXPECTED)
        self.assertEqual(preview["contract"]["plan_id"],plan)
        work.export(target,confirmed=True)
        self.assertEqual(target.read_bytes(),digital.EXPECTED)
        work.preview(source,"id,name,category","id","2")
        obligation=work.register(target,confirmed=True)
        invoice_args=dict(obligation_id=obligation["obligation_id"],
            expected_obligation_head=obligation["head_sha256"],issue_date=f.now.date().isoformat())
        with self.assertRaises(ValueError):
            guard.simulated_invoice_action("preview",plan,**invoice_args)
        evidence=f.directory/"synthetic-acceptance-claim.txt"
        evidence.write_bytes(b"synthetic claim only; not buyer acceptance")
        noted=guard.csv_obligation_action("note",plan,obligation_id=obligation["obligation_id"],
            expected_head=obligation["head_sha256"],kind="acceptance_claim_noted",
            evidence_path=evidence,confirmed=True)
        invoice_args["expected_obligation_head"]=noted["head_sha256"]
        invoice=guard.simulated_invoice_action("preview",plan,**invoice_args)
        self.assertEqual(invoice["plan_id"],plan)
        self.assertEqual(invoice["artifact_sha256"],preview["report"]["artifact_sha256"])
        record=guard.simulated_invoice_action("create",plan,**invoice_args,
            expected_invoice_id=invoice["invoice_id"],confirmed=True)
        partial=guard.simulated_invoice_action("payment",plan,invoice_id=invoice["invoice_id"],
            expected_head=record["head_sha256"],sim_reference="SIM-E2E1",amount="50.00",
            paid_on=invoice["issue_date"],confirmed=True)
        self.assertEqual(partial["simulated_received_cents"],5000)
        settled=guard.simulated_invoice_action("payment",plan,invoice_id=invoice["invoice_id"],
            expected_head=partial["head_sha256"],sim_reference="SIM-E2E2",amount="150.00",
            paid_on=invoice["issue_date"],confirmed=True)
        self.assertEqual(settled["state"],"SIMULATED_SETTLED")
        self.assertEqual(settled["simulated_outstanding_cents"],0)
        for flag in ("buyer_accepted","invoice_issued","real_receivable","payment_received",
                     "revenue_realized","funds_available","external_authority"):
            self.assertIs(settled[flag],False)
        for action in (Action.OUTREACH,Action.BID,Action.CONTRACT,Action.SIGNATURE,
                       Action.PAYMENT,Action.BROKERAGE,Action.CUSTODY,Action.INVENTORY):
            self.assertFalse(decide(action,halted=False).allowed)
        self.assertEqual(guard.operator_action("thread_history",plan,**scope),thread)
        self.assertEqual(guard.simulated_invoice_action("history",plan,invoice_id=invoice["invoice_id"]),settled)
        guard.set()
        with self.assertRaises(PermissionError):
            guard.operator_action("thread_history",plan,**scope)
        with self.assertRaises(PermissionError):
            guard.simulated_invoice_action("history",plan,invoice_id=invoice["invoice_id"])


if __name__=="__main__":
    unittest.main()
