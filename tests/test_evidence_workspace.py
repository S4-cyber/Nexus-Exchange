import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_store import ScenarioStore
from nexus_exchange.evidence_workspace import (
    EvidenceWorkspace, coverage_summary, assumption_values, reference_details, byte_result_text,
)
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW, reports
from test_owner_profile import profile


class EvidenceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.file=self.directory/"private-synthetic-filename.txt"
        self.file.write_bytes(b"synthetic commercial evidence")
        self.profile=profile()
        self.now=NOW
        self.halted=False
        self.report=reports()[0]
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.profile,halted=False)
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(self.report,now=NOW,halted=False)
            self.context=context_for(store.browse(now=NOW,profile=self.profile,
                source="sam",halted=False)["leads"][0])
            self.key=store.save(self.context,scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.workspace=EvidenceWorkspace(self.directory,self.context,self.key,
            halt_check=lambda:self.halted,clock=lambda:self.now)

    def test_coverage_and_exact_immutable_values(self):
        result=self.workspace.refresh()
        self.assertEqual(result["plan_id"],self.key)
        self.assertEqual(result["total"],17)
        self.assertEqual(result["referenced"],0)
        self.assertIn("0 / 17 referenced",coverage_summary(result))
        self.assertIn("0 independently verified",coverage_summary(result))
        fee=next(f for f in result["fields"] if f["field"]=="compensation")
        self.assertIn("200.00",assumption_values(fee))
        self.assertIn("Reference required",assumption_values(fee))
        self.assertFalse(result["external_authority"])

    def test_attach_reload_and_byte_only_result(self):
        key=self.workspace.attach("compensation",self.file)
        result=self.workspace.refresh()
        self.assertIn("1 / 17 referenced",coverage_summary(result))
        field=next(f for f in result["fields"] if f["field"]=="compensation")
        ref=field["references"][0]
        self.assertEqual(ref["evidence_id"],key)
        self.assertIn("Reference noted / unverified",assumption_values(field))
        details=reference_details(field,ref,result)
        self.assertIn(key,details)
        self.assertIn("UNVERIFIED",details)
        self.assertNotIn(str(self.file),details)
        match=self.workspace.verify("compensation",key,self.file)
        self.assertTrue(match["byte_match"])
        self.assertIn("BYTE MATCH",byte_result_text(match))
        self.assertIn("not factual verification",byte_result_text(match))
        self.file.write_bytes(b"modified")
        mismatch=self.workspace.verify("compensation",key,self.file)
        self.assertFalse(mismatch["byte_match"])
        self.assertIn("BYTE MISMATCH",byte_result_text(mismatch))
        self.assertEqual(self.workspace.refresh()["independently_verified_count"],0)

    def test_wrong_field_and_foreign_plan_never_read(self):
        key=self.workspace.attach("compensation",self.file)
        with patch("nexus_exchange.scenario_evidence.verify_reference") as read:
            with self.assertRaises(ValueError):
                self.workspace.verify("cost:software",key,self.file)
            read.assert_not_called()
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            other=store.save(self.context,scenario(compensation="201"),plan(),
                profile=self.profile,now=NOW,halted=False)
        foreign=EvidenceWorkspace(self.directory,self.context,other,halt_check=lambda:False,clock=lambda:NOW)
        self.assertEqual(foreign.refresh()["referenced"],0)
        with patch("nexus_exchange.scenario_evidence.verify_reference") as read:
            with self.assertRaises(ValueError):
                foreign.verify("compensation",key,self.file)
            read.assert_not_called()

    def test_halt_precedes_file_access(self):
        key=self.workspace.attach("compensation",self.file)
        for value in (True,None,0):
            self.halted=value
            with patch("nexus_exchange.scenario_evidence.fingerprint") as attach, \
                 patch("nexus_exchange.scenario_evidence.verify_reference") as verify:
                for action in (self.workspace.refresh,
                    lambda:self.workspace.attach("compensation",self.file),
                    lambda:self.workspace.verify("compensation",key,self.file)):
                    with self.assertRaises(PermissionError):
                        action()
                attach.assert_not_called()
                verify.assert_not_called()

    def test_profile_change_and_supersession_block_context(self):
        key=self.workspace.attach("compensation",self.file)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with patch("nexus_exchange.scenario_evidence.verify_reference") as read:
            with self.assertRaises(ValueError):
                self.workspace.verify("compensation",key,self.file)
            read.assert_not_called()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.profile,halted=False)
        later=NOW+timedelta(minutes=1)
        updated=copy.deepcopy(self.report)
        updated["leads"][0]["retrieved_at"]=later.isoformat()
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(updated,now=later,halted=False)
        self.now=later
        with self.assertRaises(ValueError):
            self.workspace.refresh()

    def test_unknown_fields_and_stale_context(self):
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            unknown=store.save(self.context,scenario(compensation=None),plan(),
                profile=self.profile,now=NOW,halted=False)
        workspace=EvidenceWorkspace(self.directory,self.context,unknown,halt_check=lambda:False,clock=lambda:NOW)
        field=next(f for f in workspace.refresh()["fields"] if f["field"]=="compensation")
        self.assertIn("Unknown",assumption_values(field))
        self.assertIn("Assumption unknown",assumption_values(field))
        with patch("nexus_exchange.scenario_evidence.fingerprint") as read:
            with self.assertRaises(ValueError):
                workspace.attach("compensation",self.file)
            read.assert_not_called()

    def test_profile_recheck_after_read(self):
        with patch.object(self.workspace,"_profile",side_effect=[self.profile,profile(hours_per_week=30)]):
            with self.assertRaises(ValueError):
                self.workspace.refresh()

    def test_foreign_context_before_attachment(self):
        wrong=dict(self.context,observation_sha256="a"*64)
        workspace=EvidenceWorkspace(self.directory,wrong,self.key,halt_check=lambda:False,clock=lambda:NOW)
        with patch("nexus_exchange.scenario_evidence.fingerprint") as read:
            with self.assertRaises(ValueError):
                workspace.attach("compensation",self.file)
            read.assert_not_called()
