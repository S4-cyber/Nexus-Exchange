import copy
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from datetime import timedelta

from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.digital_deliverable import (
    build_contract, produce_csv, verify_csv, DeliverableError, MAX_INPUT_BYTES, JSON_FORMAT, JSON_SOURCE, PROFILE_FORMAT, PROFILE_COLUMNS, RECONCILE_FORMAT, RECONCILE_REPORT,
)
from nexus_exchange.lead_store import _digest,_json
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_store import ScenarioStore
from nexus_exchange.runtime_guard import RuntimeGuard
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam

RAW=b'name,id,category\n"Beta, Inc",002,Research\nAlpha,001,Design\n'
EXPECTED=b'"id","name","category"\r\n"001","Alpha","Design"\r\n"002","Beta, Inc","Research"\r\n'
JSON_RAW=b'[{"name":"Beta, Inc","id":"002","category":"Research"},{"category":"Design","id":"001","name":"Alpha"}]'

PROFILE_RAW=b'id,name,category\n001,,A\n002, ,A\n003,Alpha,a\n004,Alpha,\n'
PROFILE_EXPECTED=(b'"column","row_count","empty_count","whitespace_only_count","nonblank_count","distinct_nonblank_count","min_chars","max_chars"\r\n'
    b'"category","4","1","0","3","2","0","1"\r\n"id","4","0","0","4","4","3","3"\r\n"name","4","1","1","2","1","0","5"\r\n')

LEFT=b'id,name,category\n001,Alpha,A\n002,Beta,B\n004,Delta,D\n'
RIGHT=b'category,name,id\nA,Alfa,001\nC,Gamma,003\nD,Delta,004\n'
RECONCILED=(b'"record_key","status","changed_field_count","changed_name","changed_category"\r\n'
    b'"001","CHANGED","1","YES","NO"\r\n"002","LEFT_ONLY","0","NOT_COMPARED","NOT_COMPARED"\r\n'
    b'"003","RIGHT_ONLY","0","NOT_COMPARED","NOT_COMPARED"\r\n"004","UNCHANGED","0","NO","NO"\r\n')


def spec(raw=RAW,**changes):
    return dict(dict(input_sha256=sha256(raw).hexdigest(),columns=["id","name","category"],
                     key_column="id",expected_rows=2),**changes)


class DigitalDeliverableTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name)
        self.now=NOW
        self.declared=profile()
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.declared,halted=False)
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(self.report,now=NOW,halted=False)
            lead=store.browse(now=NOW,source="sam",profile=self.declared,halted=False)["leads"][0]
            self.key=store.save(context_for(lead),scenario(),plan(),profile=self.declared,now=NOW,halted=False)
        self.guard=RuntimeGuard(self.directory,clock=lambda:self.now)
        self.addCleanup(self.guard.close)
        self.guard.resume()

    def contract(self,raw=RAW,**changes):
        snap=self.guard.council_action("inspect",self.key)
        return build_contract(snap,spec(raw,**changes),halted=False)

    def call(self,raw=RAW,**changes):
        return self.guard.produce_csv_deliverable(self.key,raw=raw,
            specification=spec(raw,**changes),confirmed=True)

    def scoped_args(self,raw,specification,capability_id,*,right_raw=None,cell_chars=30,input_bytes=None):
        from nexus_exchange.operator_capabilities import CSV_ID, JSON_ID
        from nexus_exchange.ranking_workspace import RankingWorkspace
        from nexus_exchange.service_handoff import review_scope
        context=self.guard.council_action("inspect",self.key)["context"]
        declaration=dict(capability_id=capability_id,
            input_format=JSON_SOURCE if capability_id==JSON_ID else "UTF8_CSV",
            input_bytes=len(raw) if input_bytes is None else input_bytes,
            max_cell_chars=cell_chars,preserve_all_fields=capability_id in (CSV_ID,JSON_ID),
            requires_deduplication=False,requires_inference=False,requires_formulas=False,
            specification=specification)
        if right_raw is not None:
            declaration["right_input_bytes"]=len(right_raw)
        review=RankingWorkspace(self.directory,halt_check=self.guard.is_set,
            clock=lambda:self.now).review_requirements(context,declaration)
        self.assertEqual(review["state"],"DECLARED_STRUCTURE_FITS")
        return dict(context=context,requirements=declaration,expected_scope=review_scope(review),
                    raw=raw,right_raw=right_raw,confirmed=True)

    def test_scoped_service_sample_all_four_actual_routes(self):
        from nexus_exchange.operator_capabilities import CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID
        for raw, specification, capability, right, expected in (
                (RAW,spec(),CSV_ID,None,EXPECTED),
                (JSON_RAW,spec(JSON_RAW),JSON_ID,None,EXPECTED),
                (PROFILE_RAW,spec(PROFILE_RAW,expected_rows=4),PROFILE_ID,None,PROFILE_EXPECTED),
                (LEFT,spec(LEFT,expected_rows=3,right_input_sha256=sha256(RIGHT).hexdigest(),
                           right_expected_rows=3),RECONCILE_ID,RIGHT,RECONCILED)):
            with self.subTest(capability=capability):
                args=self.scoped_args(raw,specification,capability,right_raw=right)
                result=self.guard.produce_scoped_service_sample(self.key,**args)
                self.assertEqual(result["review_scope_sha256"],args["expected_scope"])
                self.assertEqual(result["sample"]["artifact"],expected)
                self.assertEqual(result["sample"]["contract"]["plan_id"],self.key)
                self.assertEqual(result["sample"]["contract"]["specification"],specification)
                self.assertIs(result["external_authority"],False)
                self.assertIs(result["sample"]["report"]["buyer_accepted"],False)
                self.assertIs(result["sample"]["report"]["revenue_realized"],False)
                self.assertTrue(result["sample"]["report"]["local_criteria_passed"])
        self.assertFalse((self.directory/"operator-obligations.sqlite3").exists())

    def test_scoped_service_sample_rejects_scope_bytes_and_declared_bounds(self):
        from nexus_exchange.operator_capabilities import CSV_ID
        args=self.scoped_args(RAW,spec(),CSV_ID)
        for change in (dict(expected_scope="f"*64),
                       dict(raw=RAW.replace(b"Alpha",b"Omega")),
                       dict(context=dict(args["context"],lead_key="other")),
                       dict(requirements=dict(args["requirements"],max_cell_chars=40))):
            with self.subTest(change=list(change)),self.assertRaises(ValueError):
                self.guard.produce_scoped_service_sample(self.key,**dict(args,**change))
        for constrained in (self.scoped_args(RAW,spec(),CSV_ID,cell_chars=2),
                            self.scoped_args(RAW,spec(),CSV_ID,input_bytes=len(RAW)+1)):
            with self.assertRaises(ValueError):
                self.guard.produce_scoped_service_sample(self.key,**constrained)
        self.assertEqual(self.guard.produce_scoped_service_sample(self.key,**args)["sample"]["artifact"],EXPECTED)

    def test_scoped_service_sample_requires_confirmation_and_current_source(self):
        from nexus_exchange.operator_capabilities import CSV_ID
        args=self.scoped_args(RAW,spec(),CSV_ID)
        for confirmed in (None,False,1):
            with self.subTest(confirmed=confirmed),self.assertRaises(PermissionError):
                self.guard.produce_scoped_service_sample(self.key,**dict(args,confirmed=confirmed))
        self.now+=timedelta(days=2)
        with self.assertRaises(ValueError):
            self.guard.produce_scoped_service_sample(self.key,**args)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.guard.produce_scoped_service_sample(self.key,**args)

    def test_scoped_service_sample_withholds_result_if_source_changes_after_production(self):
        from nexus_exchange.operator_capabilities import CSV_ID
        args=self.scoped_args(RAW,spec(),CSV_ID)
        original=self.guard._csv_scoped
        def advance(*a,**kw):
            result=original(*a,**kw)
            self.now+=timedelta(days=2)
            return result
        with patch.object(self.guard,"_csv_scoped",side_effect=advance):
            with self.assertRaises(ValueError):
                self.guard.produce_scoped_service_sample(self.key,**args)
        self.assertFalse(self.guard._operator_active)

    def scoped_file_args(self,raw,specification,capability,*,right_raw=None):
        args=self.scoped_args(raw,specification,capability,right_raw=right_raw)
        args.pop("raw")
        args.pop("right_raw")
        source=self.directory/("owned.json" if args["requirements"]["input_format"]==JSON_SOURCE else "owned.csv")
        source.write_bytes(raw)
        args["source_path"]=source
        if right_raw is not None:
            right=self.directory/"owned-right.csv"
            right.write_bytes(right_raw)
            args["right_source_path"]=right
        return args

    def test_scoped_file_preview_uses_all_four_local_services(self):
        from nexus_exchange.operator_capabilities import CSV_ID, JSON_ID, PROFILE_ID, RECONCILE_ID
        for raw,specification,capability,right,expected in (
                (RAW,spec(),CSV_ID,None,EXPECTED),
                (JSON_RAW,spec(JSON_RAW),JSON_ID,None,EXPECTED),
                (PROFILE_RAW,spec(PROFILE_RAW,expected_rows=4),PROFILE_ID,None,PROFILE_EXPECTED),
                (LEFT,spec(LEFT,expected_rows=3,right_input_sha256=sha256(RIGHT).hexdigest(),
                           right_expected_rows=3),RECONCILE_ID,RIGHT,RECONCILED)):
            with self.subTest(capability=capability):
                args=self.scoped_file_args(raw,specification,capability,right_raw=right)
                result=self.guard.preview_scoped_service_files(self.key,**args)
                self.assertEqual(result["sample"]["artifact"],expected)
                self.assertEqual(result["sample"]["contract"]["specification"],specification)
                self.assertEqual(result["review_scope_sha256"],args["expected_scope"])
                self.assertIs(result["external_authority"],False)
        self.assertFalse((self.directory/"operator-obligations.sqlite3").exists())

    def test_scoped_file_preview_denies_before_file_read(self):
        from nexus_exchange.operator_capabilities import CSV_ID, RECONCILE_ID
        args=self.scoped_file_args(RAW,spec(),CSV_ID)
        reconcile=self.scoped_file_args(LEFT,spec(LEFT,expected_rows=3,
            right_input_sha256=sha256(RIGHT).hexdigest(),right_expected_rows=3),RECONCILE_ID,right_raw=RIGHT)
        with patch("nexus_exchange.deliverable_files.read_selected_csv") as read:
            for change in (dict(expected_scope="f"*64),dict(right_source_path=args["source_path"]),
                           dict(context=dict(args["context"],lead_key="other"))):
                with self.subTest(change=list(change)),self.assertRaises(ValueError):
                    self.guard.preview_scoped_service_files(self.key,**dict(args,**change))
            with self.assertRaises(ValueError):
                self.guard.preview_scoped_service_files(self.key,**dict(reconcile,right_source_path=None))
            with self.assertRaises(PermissionError):
                self.guard.preview_scoped_service_files(self.key,**dict(args,confirmed=False))
            self.now+=timedelta(days=2)
            with self.assertRaises(ValueError):
                self.guard.preview_scoped_service_files(self.key,**args)
            read.assert_not_called()
        self.assertFalse(self.guard._operator_active)

    def test_scoped_file_preview_rejects_changed_input_and_can_retry(self):
        from nexus_exchange.operator_capabilities import CSV_ID
        args=self.scoped_file_args(RAW,spec(),CSV_ID)
        args["source_path"].write_bytes(RAW.replace(b"Alpha",b"Omega"))
        with self.assertRaises(ValueError):
            self.guard.preview_scoped_service_files(self.key,**args)
        self.assertFalse(self.guard._operator_active)
        args["source_path"].write_bytes(RAW)
        self.assertEqual(self.guard.preview_scoped_service_files(self.key,**args)["sample"]["artifact"],EXPECTED)

    def test_real_saved_plan_produces_exact_artifact_and_qa(self):
        result=self.call()
        self.assertEqual(result["artifact"],EXPECTED)
        self.assertEqual(result["contract"]["plan_id"],self.key)
        self.assertEqual(result["report"]["rows"],2)
        self.assertTrue(result["report"]["local_criteria_passed"])
        self.assertEqual(result["report"]["artifact_sha256"],sha256(EXPECTED).hexdigest())
        self.assertEqual(result["report"],verify_csv(result["contract"],RAW,EXPECTED,halted=False))
        for flag in ("buyer_accepted","contract_awarded","invoice_eligible","revenue_realized",
                     "execution_eligible","external_authority","zero_capital_verified"):
            self.assertIs(result["report"][flag],False)
        self.assertEqual(self.call(),result)
        self.assertFalse((self.directory/"operator.sqlite3").exists())

    def json_call(self,raw=JSON_RAW,**changes):
        return self.guard.produce_csv_deliverable(self.key,raw=raw,
            specification=spec(raw,**changes),source_format=JSON_SOURCE,confirmed=True)

    def test_json_conversion_exact_values_and_qa(self):
        result=self.json_call()
        self.assertEqual(result["artifact"],EXPECTED)
        self.assertEqual(result["contract"]["format"],JSON_FORMAT)
        self.assertIn("NO_DUPLICATE_JSON_MEMBERS",result["report"]["checks"])
        self.assertEqual(result["report"],verify_csv(result["contract"],JSON_RAW,EXPECTED,halted=False))
        self.assertEqual(self.json_call(),result)
        self.assertFalse(result["report"]["external_authority"])
        self.assertFalse(result["report"]["buyer_accepted"])
        self.assertFalse(result["report"]["revenue_realized"])
        with self.assertRaises(DeliverableError):
            verify_csv(result["contract"],JSON_RAW,EXPECTED.replace(b"Alpha",b"Other"),halted=False)
        with self.assertRaises(DeliverableError):
            produce_csv(result["contract"],JSON_RAW+b" ",halted=False)

    def test_json_rejects_ambiguous_or_unsafe_input(self):
        for raw in (
                JSON_RAW.replace(b'"id":"002"',b'"id":"002","id":"099"'),
                JSON_RAW.replace(b'"002"',b'2'),
                JSON_RAW.replace(b'"Alpha"',b'null'),
                JSON_RAW.replace(b'"Alpha"',b'true'),
                JSON_RAW.replace(b'"Alpha"',b'["Alpha"]'),
                JSON_RAW.replace(b'"Alpha"',b'{"name":"Alpha"}'),
                JSON_RAW.replace(b'"Alpha"',b'NaN'),
                JSON_RAW.replace(b'"Alpha"',b'"=1+1"'),
                JSON_RAW.replace(b'"Alpha"',b'"\\u0000"'),
                JSON_RAW.replace(b'"001"',b'"002"'),
                JSON_RAW.replace(b'"name":"Alpha"',b'"other":"Alpha"'),
                JSON_RAW[:-1],b'{}',b'\xff'):
            with self.subTest(raw=raw),self.assertRaises(DeliverableError):
                self.json_call(raw)
        with self.assertRaises(DeliverableError):
            self.json_call(expected_rows=1)
        with self.assertRaises(DeliverableError):
            self.json_call(b"x"*(MAX_INPUT_BYTES+1))

    def test_json_file_preview_export_and_durable_obligation(self):
        from nexus_exchange.csv_workspace import CsvWorkspace
        source=self.directory/"sample.json"
        target=self.directory/"sample.csv"
        source.write_bytes(JSON_RAW)
        workspace=CsvWorkspace(self.key,action=self.guard.csv_file_action,
                               blocked_check=self.guard.is_set,source_format=JSON_SOURCE)
        reviewed=workspace.preview(source,"id,name,category","id","2")
        self.assertEqual(reviewed["artifact"],EXPECTED)
        self.assertTrue(workspace.export(target,confirmed=True)["exported"])
        self.assertEqual(target.read_bytes(),EXPECTED)
        workspace.preview(source,"id,name,category","id","2")
        saved=workspace.register(target,confirmed=True)
        self.assertFalse(saved["buyer_accepted"])
        self.assertEqual(saved["binding"]["contract"]["format"],JSON_FORMAT)
        historical=self.guard.csv_obligation_action("history",self.key,
            obligation_id=saved["obligation_id"])
        self.assertEqual(historical,saved)
        # A legacy CSV with the same output is a different source contract.
        source_csv=self.directory/"original.csv"
        source_csv.write_bytes(RAW)
        legacy=CsvWorkspace(self.key,action=self.guard.csv_file_action,blocked_check=self.guard.is_set)
        old=legacy.preview(source_csv,"id,name,category","id","2")
        self.assertEqual(old["artifact"],reviewed["artifact"])
        self.assertNotEqual(old["contract"]["contract_sha256"],reviewed["contract"]["contract_sha256"])

    def test_json_file_format_pin_halt_and_changed_source(self):
        from nexus_exchange.deliverable_files import preview_pins
        source=self.directory/"sample.json"
        target=self.directory/"sample.csv"
        source.write_bytes(JSON_RAW)
        inputs=dict(source_path=source,columns=["id","name","category"],
                    key_column="id",expected_rows=2,source_format=JSON_SOURCE)
        result=self.guard.csv_file_action("preview",self.key,confirmed=True,**inputs)
        source.write_bytes(JSON_RAW+b" ")
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("export",self.key,confirmed=True,destination_path=target,
                                       **inputs,**preview_pins(result))
        self.assertFalse(target.exists())
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("preview",self.key,confirmed=True,**dict(inputs,source_format="OTHER"))
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("preview",self.key,confirmed=True,**dict(inputs,source_format="UTF8_CSV"))
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.json_call()

    def profile_call(self,raw=PROFILE_RAW,**changes):
        return self.guard.produce_csv_deliverable(self.key,raw=raw,
            specification=spec(raw,**dict(dict(expected_rows=4),**changes)),
            operation="COLUMN_PROFILE",confirmed=True)

    def test_column_profile_exact_aggregates_and_no_source_values(self):
        result=self.profile_call()
        self.assertEqual(result["artifact"],PROFILE_EXPECTED)
        self.assertEqual(result["contract"]["format"],PROFILE_FORMAT)
        self.assertEqual(result["report"]["rows"],3)
        self.assertEqual(result["report"]["columns"],list(PROFILE_COLUMNS))
        self.assertEqual(result["report"]["key_column"],"column")
        self.assertNotIn(b"Alpha",result["artifact"])
        self.assertNotIn(b"001",result["artifact"])
        self.assertNotIn("EXACT_CELL_PRESERVATION",result["report"]["checks"])
        self.assertEqual(result["report"],verify_csv(result["contract"],PROFILE_RAW,PROFILE_EXPECTED,halted=False))
        self.assertEqual(self.profile_call(),result)
        for flag in ("external_authority","buyer_accepted","revenue_realized","invoice_eligible"):
            self.assertFalse(result["report"][flag])

    def test_column_profile_rejects_changed_output_and_unsafe_source(self):
        result=self.profile_call()
        for artifact in (PROFILE_EXPECTED.replace(b'"category","4"',b'"category","5"'),
                         PROFILE_EXPECTED.replace(b'"category","4"',b'"other","4"'),
                         PROFILE_EXPECTED.replace(b"\r\n",b"\n"),
                         PROFILE_EXPECTED.replace(b'"name","4"',b'"id","4"')):
            with self.subTest(artifact=artifact),self.assertRaises(DeliverableError):
                verify_csv(result["contract"],PROFILE_RAW,artifact,halted=False)
        for raw in (PROFILE_RAW.replace(b"Alpha",b"=1+1"),PROFILE_RAW.replace(b"004",b"003"),
                    PROFILE_RAW.replace(b"Alpha",b"\x00"),PROFILE_RAW.replace(b"category",b"extra")):
            with self.subTest(raw=raw),self.assertRaises(DeliverableError):
                self.profile_call(raw)
        with self.assertRaises(DeliverableError):
            self.profile_call(expected_rows=3)
        with self.assertRaises(DeliverableError):
            self.guard.produce_csv_deliverable(self.key,raw=JSON_RAW,specification=spec(JSON_RAW),
                source_format=JSON_SOURCE,operation="COLUMN_PROFILE",confirmed=True)

    def test_column_profile_file_registration_and_operation_pins(self):
        from nexus_exchange.csv_workspace import CsvWorkspace
        from nexus_exchange.deliverable_files import preview_pins
        source=self.directory/"profile.csv"
        target=self.directory/"report.csv"
        source.write_bytes(PROFILE_RAW)
        workspace=CsvWorkspace(self.key,action=self.guard.csv_file_action,
            blocked_check=self.guard.is_set,operation="COLUMN_PROFILE")
        reviewed=workspace.preview(source,"id,name,category","id","4")
        self.assertEqual(reviewed["artifact"],PROFILE_EXPECTED)
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("export",self.key,confirmed=True,source_path=source,
                columns=["id","name","category"],key_column="id",expected_rows=4,
                destination_path=target,**preview_pins(reviewed))
        self.assertFalse(target.exists())
        self.assertTrue(workspace.export(target,confirmed=True)["exported"])
        self.assertEqual(target.read_bytes(),PROFILE_EXPECTED)
        workspace.preview(source,"id,name,category","id","4")
        saved=workspace.register(target,confirmed=True)
        self.assertEqual(saved["binding"]["qa_report"]["rows"],3)
        self.assertEqual(saved["binding"]["contract"]["specification"]["expected_rows"],4)
        self.assertFalse(saved["buyer_accepted"])
        self.assertEqual(self.guard.csv_obligation_action("history",self.key,
            obligation_id=saved["obligation_id"]),saved)
        legacy=self.call(PROFILE_RAW,expected_rows=4)
        self.assertEqual(legacy["report"]["rows"],4)
        self.assertNotEqual(legacy["contract"]["contract_sha256"],reviewed["contract"]["contract_sha256"])
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.profile_call()

    def reconcile_call(self,left=LEFT,right=RIGHT,**changes):
        requirements=dict(expected_rows=3,right_expected_rows=3,
                          right_input_sha256=sha256(right).hexdigest())
        requirements.update(changes)
        return self.guard.produce_csv_deliverable(self.key,raw=left,right_raw=right,
            specification=spec(left,**requirements),operation="RECONCILE",confirmed=True)

    def test_reconciliation_exact_key_membership_and_field_flags(self):
        result=self.reconcile_call()
        self.assertEqual(result["artifact"],RECONCILED)
        self.assertEqual(result["contract"]["format"],RECONCILE_FORMAT)
        self.assertEqual(result["report"]["format"],RECONCILE_REPORT)
        self.assertEqual(result["report"]["right_input_sha256"],sha256(RIGHT).hexdigest())
        self.assertEqual(result["report"]["rows"],4)
        self.assertEqual(result["report"],verify_csv(result["contract"],LEFT,RECONCILED,
                                                       right_raw=RIGHT,halted=False))
        for value in (b"Alpha",b"Alfa",b"Gamma",b"Delta"):
            self.assertNotIn(value,result["artifact"])
        self.assertFalse(result["report"]["external_authority"])
        self.assertFalse(result["report"]["buyer_accepted"])
        self.assertEqual(self.reconcile_call(),result)

    def test_reconciliation_rejects_wrong_bytes_unsafe_inputs_and_wrong_flags(self):
        result=self.reconcile_call()
        for artifact in (RECONCILED.replace(b'"CHANGED","1"',b'"CHANGED","2"'),
                         RECONCILED.replace(b'"003","RIGHT_ONLY"',b'"005","RIGHT_ONLY"'),
                         RECONCILED.replace(b'"YES","NO"',b'"NO","YES"'),
                         RECONCILED.replace(b"\r\n",b"\n")):
            with self.subTest(artifact=artifact),self.assertRaises(DeliverableError):
                verify_csv(result["contract"],LEFT,artifact,right_raw=RIGHT,halted=False)
        for right in (RIGHT.replace(b"003",b"001"),RIGHT.replace(b"Alfa",b"=1+1"),
                      RIGHT.replace(b"category",b"unknown"),RIGHT.replace(b"Delta",b"\x00")):
            with self.subTest(right=right),self.assertRaises(DeliverableError):
                self.reconcile_call(right=right)
        with self.assertRaises(DeliverableError):
            verify_csv(result["contract"],LEFT,RECONCILED,right_raw=RIGHT+b"\n",halted=False)
        with self.assertRaises(DeliverableError):
            verify_csv(result["contract"],LEFT,RECONCILED,halted=False)
        with self.assertRaises(DeliverableError):
            self.reconcile_call(right_expected_rows=2000)
        with self.assertRaises(DeliverableError):
            self.guard.produce_csv_deliverable(self.key,raw=RAW,right_raw=RIGHT,
                specification=spec(),confirmed=True)

    def test_reconciliation_file_lifecycle_and_second_input_pin(self):
        from nexus_exchange.csv_workspace import CsvWorkspace
        left=self.directory/"left.csv"
        right=self.directory/"right.csv"
        target=self.directory/"difference.csv"
        left.write_bytes(LEFT); right.write_bytes(RIGHT)
        workspace=CsvWorkspace(self.key,action=self.guard.csv_file_action,
            blocked_check=self.guard.is_set,operation="RECONCILE")
        def preview():
            return workspace.preview(left,"id,name,category","id","3",
                                     right_source_path=right,right_rows="3")
        result=preview()
        self.assertEqual(result["artifact"],RECONCILED)
        right.write_bytes(RIGHT.replace(b"Alfa",b"Alpha"))
        with self.assertRaises(ValueError):
            workspace.export(target,confirmed=True)
        self.assertFalse(target.exists())
        right.write_bytes(RIGHT)
        preview()
        self.assertTrue(workspace.export(target,confirmed=True)["exported"])
        self.assertEqual(target.read_bytes(),RECONCILED)
        preview()
        saved=workspace.register(target,confirmed=True)
        self.assertEqual(saved["binding"]["qa_report"]["right_input_sha256"],sha256(RIGHT).hexdigest())
        self.assertEqual(self.guard.csv_obligation_action("history",self.key,
            obligation_id=saved["obligation_id"]),saved)
        self.assertEqual(left.read_bytes(),LEFT)
        self.assertEqual(right.read_bytes(),RIGHT)
        self.guard.set()
        with self.assertRaises(PermissionError):
            preview()

    def test_reconciliation_identical_and_key_only_inputs(self):
        key_data=b'id\n001\n002\n'
        result=self.reconcile_call(left=key_data,right=key_data,expected_rows=2,
                                   right_expected_rows=2,columns=["id"])
        self.assertEqual(result["artifact"],b'"record_key","status","changed_field_count"\r\n'
                         b'"001","UNCHANGED","0"\r\n"002","UNCHANGED","0"\r\n')

    def test_changed_input_or_artifact_rejected(self):
        contract=self.contract()
        with self.assertRaisesRegex(DeliverableError,"FINGERPRINT"):
            produce_csv(contract,RAW.replace(b"Alpha",b"Gamma"),halted=False)
        for artifact in (EXPECTED.replace(b"Alpha",b"Gamma"),EXPECTED.replace(b'"001"',b'"003"'),
                         EXPECTED.replace(b"\r\n",b"\n"),
                         b'"id","name","category"\r\n"002","Beta, Inc","Research"\r\n"001","Alpha","Design"\r\n'):
            with self.subTest(artifact=artifact),self.assertRaises(DeliverableError):
                verify_csv(contract,RAW,artifact,halted=False)

    def test_reject_formulas_controls_duplicate_keys_and_width(self):
        for raw in (RAW.replace(b"Alpha",b"=1+1"),RAW.replace(b"Alpha",b"  @SUM(1)"),
                    RAW.replace(b"Alpha","＋1".encode()),RAW.replace(b"Alpha",b"\x00x"),
                    RAW.replace(b"001",b"002"),RAW.replace(b"001",b""),
                    RAW.replace(b"001",b" 001"),RAW.replace(b"Alpha,001,Design",b"Alpha,001"),
                    RAW.replace(b"Alpha",b'"unclosed')):
            with self.subTest(raw=raw),self.assertRaises(DeliverableError):
                self.call(raw)

    def test_unknown_header_row_count_and_bounds(self):
        for raw,changes in ((RAW.replace(b"name,id,category",b"name,id,extra"),{}),
                            (RAW,dict(expected_rows=1)),(RAW,dict(expected_rows=True)),
                            (RAW,dict(columns=["id","id","category"])),
                            (RAW,dict(key_column="unknown")),
                            (b"x"*(MAX_INPUT_BYTES+1),{})):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.call(raw,**changes)

    def test_scope_and_authority_tampering(self):
        contract=self.contract()
        for changed in (dict(contract,external_authority=True),
                        dict(contract,contract_sha256="0"*64),
                        dict(contract,plan_id="0"*64)):
            with self.assertRaises(DeliverableError):
                produce_csv(changed,RAW,halted=False)
        # Self-consistent hash still cannot turn a flag into authority.
        forged=dict(contract,buyer_accepted=True)
        forged["contract_sha256"]=_digest(_json({k:v for k,v in forged.items() if k!="contract_sha256"}))
        with self.assertRaises(DeliverableError):
            produce_csv(forged,RAW,halted=False)

    def test_halt_unknown_and_mid_processing(self):
        contract=self.contract()
        for halted in (None,True,0):
            with self.assertRaises(PermissionError):
                produce_csv(contract,RAW,halted=halted)
        calls=0
        def stop():
            nonlocal calls
            calls+=1
            return calls>=4
        with self.assertRaises(PermissionError):
            produce_csv(contract,RAW,halted=False,halt_check=stop)

    def test_runtime_owner_confirmation_and_active_task(self):
        for confirmed in (None,False,1,"true"):
            with self.assertRaises(PermissionError):
                self.guard.produce_csv_deliverable(self.key,raw=RAW,specification=spec(),confirmed=confirmed)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(PermissionError):
                pool.submit(self.call).result(timeout=5)
        event=dict(task_id="worker",target="Synthetic",timestamp=self.now.isoformat())
        self.guard.events.append(dict(event,state="queued"))
        try:
            with self.assertRaises(PermissionError):
                self.call()
        finally:
            self.guard.events.append(dict(event,state="cancelled"))
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.call()

    def test_profile_and_superseded_observation_reject(self):
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.call()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.declared,halted=False)
        self.now+=timedelta(minutes=1)
        updated=copy.deepcopy(self.report)
        updated["leads"][0]["retrieved_at"]=self.now.isoformat()
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(updated,now=self.now,halted=False)
        with self.assertRaises(ValueError):
            self.call()

    def test_source_hold_prevents_contract(self):
        self.now+=timedelta(days=2)
        with self.assertRaises(ValueError):
            self.call()

    def test_reentry_and_halt_after_production(self):
        def interrupted(*args,**kwargs):
            result=produce_csv(*args,**kwargs)
            with self.assertRaises(PermissionError):
                self.guard.resume()
            with self.assertRaises(PermissionError):
                self.guard.close()
            self.guard.set()
            return result
        with patch("nexus_exchange.digital_deliverable.produce_csv",side_effect=interrupted):
            with self.assertRaises(PermissionError):
                self.call()
        self.assertTrue(self.guard.is_set())
        self.assertFalse(self.guard._operator_active)

if __name__=="__main__":
    unittest.main()
