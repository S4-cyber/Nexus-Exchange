import copy
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import Mock
from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.ranking_workspace import (
    RankingWorkspace, report_summary, row_details, row_values, display_amount, display_wait,
)
from nexus_exchange.scenario_store import ScenarioStore
import test_sam_search as sam
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW
from test_owner_profile import profile


class RankingWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.profile=profile()
        self.now=NOW
        self.halted=False
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1),sam.notice(2)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(self.profile,halted=False)
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(self.report,now=NOW,halted=False)
            lead=store.browse(now=NOW,profile=self.profile,source="sam",halted=False)["leads"][0]
            self.key=store.save(context_for(lead),scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.workspace=RankingWorkspace(self.directory,halt_check=lambda:self.halted,clock=lambda:self.now)

    def test_refresh_and_preserve_rank_order(self):
        result=self.workspace.refresh()
        self.assertEqual(result["returned"],2)
        self.assertEqual(result["rows"][0]["plan_id"],self.key)
        self.assertEqual(result["rows"][0]["review_tier"],"MODEL_FITS_UNVERIFIED")
        self.assertEqual(result["rows"][1]["review_tier"],"MODEL_UNRESOLVED")
        self.assertFalse(result["external_authority"])
        self.assertIn("Genesis",report_summary(result))
        self.assertIn("2 shown / 2 evaluated / 2 matched",report_summary(result))
        self.assertIn("Not a global ranking",report_summary(result))
        self.assertIn("UNVERIFIED",row_details(result["rows"][0],result))
        self.assertIn(self.key,row_details(result["rows"][0],result))
        self.assertIn("Unknown",row_values(result["rows"][1]))

    def test_filter_and_truncation_disclosures(self):
        result=self.workspace.refresh(source="sam",limit=1,scan_limit=1)
        self.assertTrue(result["scan_truncated"])
        self.assertIn("Scan truncated",report_summary(result))
        result=self.workspace.refresh(limit=1,scan_limit=2)
        self.assertTrue(result["output_truncated"])
        self.assertIn("Display truncated",report_summary(result))
        self.assertEqual(self.workspace.refresh(query="not matching")["returned"],0)
        self.assertEqual(self.workspace.refresh(source="ted")["returned"],0)

    def test_selection_rechecks_current_context(self):
        selected=self.workspace.refresh()["rows"][0]
        lead=self.workspace.resolve(selected["context"])
        self.assertEqual(context_for(lead),selected["context"])
        later=NOW+timedelta(minutes=1)
        newer=copy.deepcopy(self.report)
        for row in newer["leads"]:
            row["retrieved_at"]=later.isoformat()
        with ScenarioStore(self.directory/"scout-leads.sqlite3") as store:
            store.record(newer,now=later,halted=False)
        self.now=later
        with self.assertRaises(ValueError):
            self.workspace.resolve(selected["context"])
        self.assertTrue(all(row["plan_id"] is None for row in self.workspace.refresh()["rows"]))

    def test_profile_changes_do_not_inherit_previous_scenarios(self):
        selected=self.workspace.refresh()["rows"][0]
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(profile(mode="catalyst",budget="50"),halted=False)
        with self.assertRaises(ValueError):
            self.workspace.resolve(selected["context"])
        result=self.workspace.refresh()
        self.assertEqual(result["pathway"],"catalyst")
        self.assertTrue(all(row["plan_id"] is None for row in result["rows"]))

    def test_halt_and_profile_clear(self):
        context=self.workspace.refresh()["rows"][0]["context"]
        for value in (True,None,0):
            self.halted=value
            with self.assertRaises(PermissionError):
                self.workspace.refresh()
            with self.assertRaises(PermissionError):
                self.workspace.resolve(context)
        self.halted=False
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.clear(halted=False)
        with self.assertRaises(ValueError):
            self.workspace.refresh()

    def test_freshness_reassessment(self):
        self.now+=timedelta(days=2)
        result=self.workspace.refresh()
        row=next(row for row in result["rows"] if row["plan_id"]==self.key)
        self.assertEqual(row["review_tier"],"SOURCE_REVIEW_REQUIRED")
        self.assertIn("OBSERVATION_STALE",row_details(row,result))

    def test_display_does_not_round_to_zero_or_infer_missing_values(self):
        self.assertEqual(display_amount(None),"Unknown")
        self.assertEqual(display_amount(Decimal("0.00000001")),"0.00000001")
        self.assertEqual(display_amount(Decimal("0")),"0.00")
        self.assertEqual(display_amount(Decimal("-5")),"-5.00")
        self.assertEqual(display_wait(None),"Unknown")
        self.assertEqual(display_wait(-1),"Past modeled collection")
        self.assertEqual(display_wait(86400000001),"1d 1h")
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(display_amount(Decimal("12345.6789")),"12345.6789")

    def test_profile_changed_during_refresh_rejects_snapshot(self):
        original=self.workspace._profile
        replacement=profile(mode="catalyst",budget="50")
        from unittest.mock import patch
        with patch.object(self.workspace,"_profile",side_effect=[original(),replacement]):
            with self.assertRaises(ValueError):
                self.workspace.refresh()
