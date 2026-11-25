import copy
import unittest

import test_digital_deliverable as fixture
from nexus_exchange.csv_workspace import CsvWorkspace, preview_text
from nexus_exchange.digital_deliverable import (
    FORMAT, JSON_FORMAT, PROFILE_FORMAT, RECONCILE_FORMAT,
)
from nexus_exchange.lead_store import _digest, _json
from nexus_exchange.operator_capabilities import catalog
from nexus_exchange.operator_workflow import (
    workflow_template, workflow_plan, preview_progress, export_progress,
    historical_progress, template_text, progress_text,
)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.DigitalDeliverableTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.directory=self.fixture.directory

    def workspace(self,action=None):
        source=self.directory/"input.csv"
        source.write_bytes(fixture.RAW)
        workspace=CsvWorkspace(self.fixture.key,action=action or self.guard.csv_file_action,
                               blocked_check=self.guard.is_set)
        return workspace,source

    def test_all_four_templates_are_ordered_bounded_and_advisory(self):
        entries=catalog(halted=False)["capabilities"]
        self.assertEqual(len(entries),4)
        for item in entries:
            template=workflow_template(item["contract_format"],halted=False)
            self.assertEqual(template["template_sha256"],item["workflow_template_sha256"])
            self.assertEqual(template["source_count"],2 if item["contract_format"]==RECONCILE_FORMAT else 1)
            seen=set()
            for task in template["tasks"]:
                self.assertNotIn(task["task_id"],seen)
                self.assertTrue(set(task["requires"])<=seen)
                seen.add(task["task_id"])
            self.assertEqual(len(seen),10)
            self.assertFalse(template["external_authority"])
            self.assertFalse(template["commercial_delivery_completed"])
            self.assertNotIn("EXPORT",template["tasks"][-2]["requires"])
            self.assertIn("planned, not executed",template_text(item["contract_format"],halted=False))
        for invalid in (None,"other",123):
            with self.assertRaises(ValueError):
                workflow_template(invalid,halted=False)

    def test_exact_contract_plans_for_each_real_service(self):
        results=[self.fixture.call(),self.fixture.json_call(),
                 self.fixture.profile_call(),self.fixture.reconcile_call()]
        ids=set()
        for result,fmt in zip(results,(FORMAT,JSON_FORMAT,PROFILE_FORMAT,RECONCILE_FORMAT)):
            progress=preview_progress(result,halted=False)
            plan=progress["workflow"]
            self.assertEqual(plan["template"]["contract_format"],fmt)
            self.assertEqual(plan["contract_sha256"],result["contract"]["contract_sha256"])
            self.assertEqual(plan["required_qa_checks"],result["report"]["checks"])
            self.assertEqual(plan,workflow_plan(result["contract"],halted=False))
            self.assertEqual(progress["task_states"]["QA"],"LOCAL_PREVIEW_PASSED")
            self.assertEqual(progress["task_states"]["REVIEW"],"REVIEW_REQUIRED")
            self.assertEqual(progress["task_states"]["EXTERNAL_HOLD"],"NOT_AUTHORIZED")
            self.assertFalse(progress["buyer_accepted"])
            self.assertIn("WORKFLOW",preview_text(result))
            self.assertEqual(progress,preview_progress(result,halted=False))
            ids.add(plan["workflow_sha256"])
        self.assertEqual(len(ids),4)

    def test_metadata_tamper_rejected_even_with_recomputed_digest(self):
        result=self.fixture.call()
        for change in (dict(checks=[]),dict(input_sha256="0"*64),
                       dict(rows=999),dict(external_authority=True)):
            bad=copy.deepcopy(result)
            bad["report"].update(change)
            bad["report"]["report_sha256"]=_digest(_json({
                k:v for k,v in bad["report"].items() if k!="report_sha256"}))
            with self.subTest(change=change),self.assertRaises(ValueError):
                preview_progress(bad,halted=False)

    def test_native_workspace_progress_and_historical_reconstruction(self):
        work,source=self.workspace()
        target=self.directory/"out.csv"
        result=work.preview(source,"id,name,category","id","2")
        reviewed=work.progress
        self.assertEqual(reviewed,preview_progress(result,halted=False))
        exported=work.export(target,confirmed=True)
        self.assertFalse(work.ready)
        self.assertEqual(work.progress,export_progress(result,exported,halted=False))
        self.assertEqual(work.progress["task_states"]["EXPORT"],"LOCAL_EXPORT_REPORTED")
        self.assertEqual(work.progress["task_states"]["REGISTER"],"REPREVIEW_AND_CONFIRM_REQUIRED")
        work.preview(source,"id,name,category","id","2")
        record=work.register(target,confirmed=True)
        progress=historical_progress(record,self.fixture.key,halted=False)
        self.assertEqual(work.progress,progress)
        self.assertEqual(progress["workflow"],reviewed["workflow"])
        self.assertEqual(progress["task_states"]["EXPORT"],"PUBLICATION_NOT_ESTABLISHED")
        self.assertEqual(progress["task_states"]["REGISTER"],"LOCAL_REGISTRATION_RECORDED")
        self.assertFalse(progress["human_review_verified"])
        self.assertFalse(progress["commercial_delivery_completed"])
        self.assertIn("Publication not established",progress_text(progress))
        fetched=self.guard.csv_obligation_action("history",self.fixture.key,
            obligation_id=record["obligation_id"])
        self.assertEqual(historical_progress(fetched,self.fixture.key,halted=False),progress)

    def test_stale_preview_and_halt_clear_local_projection(self):
        work,source=self.workspace()
        target=self.directory/"out.csv"
        work.preview(source,"id,name,category","id","2")
        # Caller mutation cannot alter the internal progress.
        detached=work.progress
        detached["task_states"]["QA"]="FORGED"
        self.assertNotEqual(work.progress,detached)
        source.write_bytes(fixture.RAW.replace(b"Alpha",b"Gamma"))
        with self.assertRaises(ValueError):
            work.export(target,confirmed=True)
        self.assertIsNone(work.progress)
        self.assertFalse(target.exists())
        work.preview(source,"id,name,category","id","2")
        self.guard.set()
        with self.assertRaises(PermissionError):
            _=work.progress
        self.assertFalse(work.ready)
        for state in (True,None,0):
            with self.assertRaises(PermissionError):
                workflow_template(FORMAT,halted=state)

    def test_export_callback_metadata_must_match_exact_preview(self):
        def action(kind,plan_id,**inputs):
            result=self.guard.csv_file_action(kind,plan_id,**inputs)
            if kind=="export":
                result["report"]=dict(result["report"],rows=99)
            return result
        work,source=self.workspace(action)
        target=self.directory/"out.csv"
        work.preview(source,"id,name,category","id","2")
        with self.assertRaises(ValueError):
            work.export(target,confirmed=True)
        self.assertFalse(work.ready)
        self.assertIsNone(work.progress)
        # The local file may already have been published. Do not delete it.
        self.assertTrue(target.exists())


if __name__=="__main__":
    unittest.main()
