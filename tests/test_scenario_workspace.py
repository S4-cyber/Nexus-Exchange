import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from nexus_exchange.checklist_store import context_for
from nexus_exchange.lead_store import LeadStore
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_workspace import (
    ScenarioWorkspace, blank_fields, parse_fields, fields_for, summary_text,
)
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW, reports
from test_owner_profile import profile


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.profile=profile(mode="genesis",budget="0",hours_per_week=20)
        self.stopped=False
        self.now=NOW
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(self.profile,halted=False)
        with LeadStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(reports()[0],now=NOW,halted=False)
            self.row=store.browse(now=NOW,source="sam",profile=self.profile,halted=False)["leads"][0]
        self.workspace=ScenarioWorkspace(self.directory,context_for(self.row),
            halt_check=lambda:self.stopped,clock=lambda:self.now)
        self.fields=fields_for(scenario(),plan())

    def test_blank_unknown_never_zero(self):
        a,b=parse_fields(blank_fields())
        self.assertIsNone(a["compensation"])
        self.assertTrue(all(v is None for v in a["costs"].values()))
        self.assertIsNone(a["delivery_days"])
        self.assertIsNone(b["delivery_start"])

    def test_roundtrip_and_strict_input(self):
        a,b=parse_fields(self.fields)
        self.assertEqual(a,scenario())
        self.assertEqual(b,plan())
        for key,value in (("labor_hours","-1"),("labor_hours","1.5"),
                          ("probability_delivery_bps","10001"),("compensation","1e5"),
                          ("delivery_start","tomorrow"),("cost:software","-1")):
            with self.subTest(key=key),self.assertRaises(ValueError):
                parse_fields(dict(self.fields,**{key:value}))
        with self.assertRaises(ValueError):
            parse_fields(dict(self.fields,extra="true"))

    def test_save_reload_and_fresh_summary(self):
        self.assertEqual(self.workspace.list(),[])
        key=self.workspace.save(self.fields)
        rows=self.workspace.list()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["plan_id"],key)
        self.assertEqual(self.workspace.load(key),fields_for(rows[0]["scenario"],rows[0]["plan"]))
        result=self.workspace.evaluate(key)
        self.assertFalse(result["execution_eligible"])
        self.assertIn("UNVERIFIED",summary_text(result))
        self.assertIn("120",summary_text(result))
        self.now+=timedelta(days=7)
        late=self.workspace.evaluate(key)
        self.assertFalse(late["schedule"]["modeled_submission_fit"])
        self.assertIn("OBSERVATION_STALE",summary_text(late))

    def test_save_does_not_evaluate_or_authorize(self):
        key=self.workspace.save(blank_fields())
        result=self.workspace.evaluate(key)
        self.assertIsNone(result["cash"]["modeled_expected_net"])
        self.assertIn("Unknown",summary_text(result))
        self.assertFalse(result["external_authority"])

    def test_profile_reload_and_scope(self):
        key=self.workspace.save(self.fields)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(profile(mode="genesis",budget="0",hours_per_week=30),halted=False)
        for action in (self.workspace.list,lambda:self.workspace.load(key),
                       lambda:self.workspace.evaluate(key),lambda:self.workspace.save(self.fields)):
            with self.assertRaises(ValueError):
                action()

    def test_halt_precedes_every_operation(self):
        key=self.workspace.save(self.fields)
        for state in (True,None,0):
            self.stopped=state
            for action in (self.workspace.list,lambda:self.workspace.load(key),
                           lambda:self.workspace.evaluate(key),lambda:self.workspace.save(self.fields)):
                with self.assertRaises(PermissionError):
                    action()

    def test_foreign_saved_plan_rejected(self):
        key=self.workspace.save(self.fields)
        with LeadStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(reports()[3],now=NOW,halted=False)
            row=store.browse(now=NOW,source="canada",profile=self.profile,halted=False)["leads"][0]
        other=ScenarioWorkspace(self.directory,context_for(row),halt_check=lambda:False,clock=lambda:NOW)
        with self.assertRaises(ValueError):
            other.load(key)
        with self.assertRaises(ValueError):
            other.evaluate(key)
