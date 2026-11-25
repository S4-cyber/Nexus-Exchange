import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange import sam_search, usaspending_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_evidence import ScenarioEvidenceStore, ASSUMPTION_FIELDS
from nexus_exchange.council_attempts import CouncilAttemptStore
from nexus_exchange.scenario_council import ScenarioCouncil
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam
import test_usaspending_search as spending


class ScenarioCouncilTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.path=self.directory/"scout-leads.sqlite3"
        self.evidence=self.directory/"synthetic-private.txt"
        self.evidence.write_bytes(b"synthetic reference, not factual proof")
        self.profile=profile()
        self.now=NOW
        self.halted=False
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(self.profile,halted=False)
        with ScenarioEvidenceStore(self.path) as store:
            store.record(self.report,now=NOW,halted=False)
            self.context=context_for(store.browse(now=NOW,source="sam",profile=self.profile,
                halted=False)["leads"][0])
            self.key=store.save(self.context,scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.council=ScenarioCouncil(self.directory,halt_check=lambda:self.halted,clock=lambda:self.now)

    def attach_all(self,key=None):
        with ScenarioEvidenceStore(self.path) as store:
            for field in ASSUMPTION_FIELDS:
                store.attach(self.key if key is None else key,field,self.evidence,
                    profile=self.profile,now=self.now,halted=False)

    def save(self,raw=None,timing=None):
        with ScenarioEvidenceStore(self.path) as store:
            return store.save(self.context,scenario() if raw is None else raw,
                plan() if timing is None else timing,profile=self.profile,now=self.now,halted=False)

    def checks(self,report):
        return {item["criterion"]:item["state"] for item in report["criteria"]}

    def test_inspection_is_not_an_attempt(self):
        report=self.council.inspect(self.key)
        self.assertEqual(report["plan_id"],self.key)
        self.assertEqual(report["referenced"],0)
        self.assertEqual(report["independently_verified_count"],0)
        self.assertEqual(self.checks(report),{
            "source_and_capability":"LOCAL_CHECK_FITS","financial_model":"LOCAL_CHECK_FITS",
            "delivery_schedule":"LOCAL_CHECK_FITS","collection_timing":"LOCAL_CHECK_FITS",
            "reference_coverage":"UNRESOLVED"})
        self.assertFalse(report["external_authority"])
        self.assertFalse((self.directory/"council.sqlite3").exists())
        with self.assertRaises(ValueError):
            self.council.run_once(self.key)

    def test_reference_coverage_can_change_without_resetting_task(self):
        state=self.council.register(self.key)
        self.assertEqual(state["attempts_used"],0)
        first=self.council.run_once(self.key)
        self.assertEqual(first["review"]["status"],"NEEDS_EVIDENCE")
        self.assertEqual(first["ledger"]["attempts_used"],1)
        self.attach_all()
        same=self.council.register(self.key)
        self.assertEqual(same["task_id"],state["task_id"])
        self.assertEqual(same["contract_sha256"],state["contract_sha256"])
        second=self.council.run_once(self.key)
        self.assertEqual(second["review"]["status"],"ADVANCE_REVIEW_ONLY")
        self.assertEqual(second["ledger"]["attempts_used"],2)
        self.assertEqual(second["snapshot"]["referenced"],17)
        self.assertEqual(second["snapshot"]["independently_verified_count"],0)
        for flag in ("external_authority","commercial_facts_verified","execution_eligible","release_eligible"):
            self.assertIs(second[flag],False)
        with self.assertRaises(PermissionError):
            self.council.run_once(self.key)

    def test_three_missing_attempts_survive_reopen(self):
        self.council.register(self.key)
        for i in range(1,4):
            adapter=ScenarioCouncil(self.directory,halt_check=lambda:False,clock=lambda:self.now)
            result=adapter.run_once(self.key)
            self.assertEqual(result["ledger"]["attempts_used"],i)
            self.assertEqual(result["ledger"]["state"],"ESCALATE" if i==3 else "NEEDS_EVIDENCE")
            self.now+=timedelta(seconds=1)
        self.attach_all()
        self.assertEqual(self.council.register(self.key)["state"],"ESCALATE")
        with self.assertRaises(PermissionError):
            self.council.run_once(self.key)

    def test_nonpositive_return_and_unknown_costs(self):
        loss=self.save(scenario(compensation="0"))
        self.assertEqual(self.checks(self.council.inspect(loss))["financial_model"],"LOCAL_CHECK_FAILS")
        self.council.register(loss)
        self.assertEqual(self.council.run_once(loss)["review"]["status"],"RETRY")
        costs=scenario()["costs"]
        costs["software"]=None
        unknown=self.save(scenario(costs=costs))
        self.assertEqual(self.checks(self.council.inspect(unknown))["financial_model"],"UNRESOLVED")

    def test_zero_capital_rejects_any_positive_exposure(self):
        costs=scenario()["costs"]
        costs["software"]="0.01"
        key=self.save(scenario(costs=costs))
        self.assertEqual(self.checks(self.council.inspect(key))["financial_model"],"LOCAL_CHECK_FAILS")

    def test_unknown_payment_and_delivery_constraints(self):
        key=self.save(scenario(payment_days_after_delivery=None),plan(delivery_deadline=None))
        checks=self.checks(self.council.inspect(key))
        self.assertEqual(checks["delivery_schedule"],"UNRESOLVED")
        self.assertEqual(checks["collection_timing"],"UNRESOLVED")
        key=self.save(timing=plan(preparation_days=7))
        self.assertEqual(self.checks(self.council.inspect(key))["delivery_schedule"],"LOCAL_CHECK_FAILS")

    def test_stale_observation_veto_even_with_full_coverage(self):
        self.attach_all()
        self.council.register(self.key)
        self.now+=timedelta(days=2)
        result=self.council.run_once(self.key)
        self.assertEqual(result["review"]["status"],"RETRY")
        self.assertEqual(self.checks(result["snapshot"])["source_and_capability"],"LOCAL_CHECK_FAILS")
        self.assertIn("OBSERVATION_STALE",result["snapshot"]["reasons"])

    def test_historical_awards_never_pass_source_gate(self):
        report=usaspending_search.search(spending.QUERY,approved=True,halt_check=lambda:False,
            clock=lambda:NOW,transport=Mock(return_value=(200,spending.page([spending.award()]))))
        with ScenarioEvidenceStore(self.path) as store:
            store.record(report,now=NOW,halted=False)
            lead=store.browse(now=NOW,source="usaspending",profile=self.profile,halted=False)["leads"][0]
            key=store.save(context_for(lead),scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.assertEqual(self.checks(self.council.inspect(key))["source_and_capability"],"LOCAL_CHECK_FAILS")

    def test_changed_profile_and_superseded_observation_block_before_reservation(self):
        registered=self.council.register(self.key)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.council.run_once(self.key)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(self.profile,halted=False)
        updated=copy.deepcopy(self.report)
        self.now+=timedelta(minutes=1)
        updated["leads"][0]["retrieved_at"]=self.now.isoformat()
        with ScenarioEvidenceStore(self.path) as store:
            store.record(updated,now=self.now,halted=False)
        with self.assertRaises(ValueError):
            self.council.run_once(self.key)
        with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
            self.assertEqual(store.status(registered["task_id"],halted=False)["attempts_used"],0)

    def test_halt_and_corruption_block_before_attempt(self):
        registered=self.council.register(self.key)
        for state in (True,None,0):
            self.halted=state
            for action in (self.council.inspect,self.council.register,self.council.run_once):
                with self.assertRaises(PermissionError):
                    action(self.key)
        self.halted=False
        with ScenarioEvidenceStore(self.path) as store:
            store.db.execute("UPDATE scout_scenarios_v1 SET payload='{}' WHERE plan_id=?",(self.key,))
        with self.assertRaises(ValueError):
            self.council.run_once(self.key)
        with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
            self.assertEqual(store.status(registered["task_id"],halted=False)["attempts_used"],0)

    def test_distinct_saved_plan_gets_distinct_task_not_agent_allocated(self):
        first=self.council.register(self.key)
        other=self.save(scenario(compensation="201"))
        second=self.council.register(other)
        self.assertNotEqual(first["task_id"],second["task_id"])
        with self.assertRaises(ValueError):
            self.council.register("a"*64)
        self.assertEqual(second["attempts_used"],0)

    def test_no_artifact_or_local_path_persisted_in_council_ledger(self):
        self.attach_all()
        self.council.register(self.key)
        result=self.council.run_once(self.key)
        self.assertNotIn(str(self.evidence),str(result))
        self.assertNotIn("synthetic reference, not factual proof",str(result))
        with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
            raw=store.db.execute("SELECT payload FROM council_attempts_v1").fetchone()[0]
            self.assertNotIn("compensation",raw)
            self.assertNotIn(str(self.evidence),raw)
            self.assertIn(result["report_sha256"],raw)

    def test_snapshot_fingerprint_is_current_but_task_identity_is_stable(self):
        from nexus_exchange.lead_store import _digest, _json
        first=self.council.inspect(self.key)
        self.assertEqual(first["snapshot_sha256"],_digest(_json(
            {k:v for k,v in first.items() if k!="snapshot_sha256"})))
        self.now+=timedelta(hours=1)
        later=self.council.inspect(self.key)
        self.assertEqual(first["task_id"],later["task_id"])
        self.assertEqual(first["policy_sha256"],later["policy_sha256"])
        self.assertNotEqual(first["snapshot_sha256"],later["snapshot_sha256"])
        self.assertNotEqual(first["modeled_collection_wait_us"],later["modeled_collection_wait_us"])

    def test_profile_drift_after_commit_withholds_result_but_preserves_attempt(self):
        state=self.council.register(self.key)
        with patch.object(self.council,"_profile",side_effect=[
            self.profile,self.profile,profile(hours_per_week=30)]):
            with self.assertRaises(ValueError):
                self.council.run_once(self.key)
        with CouncilAttemptStore(self.directory/"council.sqlite3") as store:
            historical=store.status(state["task_id"],halted=False)
            self.assertEqual(historical["attempts_used"],1)
            self.assertEqual(historical["state"],"NEEDS_EVIDENCE")
            self.assertFalse(historical["external_authority"])

    def test_declared_classification_mismatch_is_a_source_hold(self):
        changed=profile(naics=["111111"],keywords=[])
        with ProfileStore(self.directory/"owner-profile.sqlite3") as profiles:
            profiles.save(changed,halted=False)
        with ScenarioEvidenceStore(self.path) as store:
            lead=store.browse(now=NOW,source="sam",profile=changed,halted=False)["leads"][0]
            key=store.save(context_for(lead),scenario(),plan(),profile=changed,now=NOW,halted=False)
        report=self.council.inspect(key)
        self.assertEqual(self.checks(report)["source_and_capability"],"LOCAL_CHECK_FAILS")
        self.assertIn("CLASSIFICATION_MISMATCH",report["reasons"])
