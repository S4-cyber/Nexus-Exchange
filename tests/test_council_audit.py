import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from nexus_exchange import sam_search
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import ProfileStore
from nexus_exchange.scenario_evidence import ScenarioEvidenceStore, ASSUMPTION_FIELDS
from nexus_exchange.council_attempts import CouncilAttemptStore
from nexus_exchange.scenario_council import ScenarioCouncil
from nexus_exchange.council_audit import validate_snapshot
from nexus_exchange.lead_store import _json, _digest
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_owner_profile import profile
from test_lead_store import NOW
import test_sam_search as sam


class CouncilAuditTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.archive=self.directory/"scout-leads.sqlite3"
        self.db=self.directory/"council.sqlite3"
        self.profile=profile()
        self.now=NOW
        self.halted=False
        self.file=self.directory/"private-synthetic.txt"
        self.file.write_bytes(b"synthetic evidence content")
        self.report=sam_search.search(sam.QUERY,sam.KEY,
            transport=Mock(return_value=(200,sam.page([sam.notice(1)]))),
            approved=True,halt_check=lambda:False,clock=lambda:NOW)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(self.profile,halted=False)
        with ScenarioEvidenceStore(self.archive) as store:
            store.record(self.report,now=NOW,halted=False)
            self.context=context_for(store.browse(now=NOW,source="sam",profile=self.profile,
                halted=False)["leads"][0])
            self.key=store.save(self.context,scenario(),plan(),profile=self.profile,now=NOW,halted=False)
        self.council=ScenarioCouncil(self.directory,halt_check=lambda:self.halted,clock=lambda:self.now)
        self.task=self.council.register(self.key)["task_id"]

    def run_review(self):
        return self.council.run_once(self.key)

    def history(self):
        return self.council.history(self.key)

    def test_roundtrip_preserves_exact_snapshot_and_review(self):
        result=self.run_review()
        reopened=ScenarioCouncil(self.directory,halt_check=lambda:False,clock=lambda:self.now)
        history=reopened.history(self.key)
        row=history["attempts"][0]
        self.assertEqual(row["audit_state"],"RECORDED")
        audit=row["audit"]
        self.assertEqual(_json(audit["snapshot"]),_json(result["snapshot"]))
        self.assertEqual(_json(audit["review"]),_json(result["review"]))
        self.assertEqual(audit["report_sha256"],result["report_sha256"])
        self.assertEqual(row["audit_sha256"],_digest(_json(audit)))
        self.assertEqual(audit["reservation_id"],row["reservation_id"])
        self.assertTrue(history["historical_only"])
        self.assertFalse(history["external_authority"])
        self.assertFalse(history["current_decision"])

    def test_reference_fingerprints_and_multiple_attempts(self):
        first=self.run_review()
        self.now+=timedelta(seconds=1)
        with ScenarioEvidenceStore(self.archive) as store:
            for field in ASSUMPTION_FIELDS:
                store.attach(self.key,field,self.file,profile=self.profile,now=self.now,halted=False)
        second=self.run_review()
        history=self.history()
        self.assertEqual(history["attempts_used"],2)
        self.assertEqual(history["attempts"][0]["audit"]["snapshot"]["referenced"],0)
        snap=history["attempts"][1]["audit"]["snapshot"]
        self.assertEqual(snap["referenced"],17)
        self.assertEqual(len(snap["reference_ids"]["compensation"]),1)
        self.assertEqual(snap["independently_verified_count"],0)
        self.assertNotEqual(first["snapshot"]["snapshot_sha256"],second["snapshot"]["snapshot_sha256"])
        self.assertNotIn(str(self.file),_json(history))
        self.assertNotIn("synthetic evidence content",_json(history))

    def test_historical_review_survives_profile_change_and_expiry(self):
        self.run_review()
        self.now+=timedelta(days=8)
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.council.inspect(self.key)
        self.assertEqual(self.history()["attempts"][0]["audit"]["snapshot"]["evaluated_at"],
                         NOW.isoformat(timespec="microseconds"))
        self.assertFalse(self.history()["current_decision"])

    def test_insert_failure_never_completes_attempt(self):
        with CouncilAttemptStore(self.db) as store:
            store.db.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON council_review_audit_v1
                BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_review()
        with CouncilAttemptStore(self.db) as store:
            self.assertEqual(store.status(self.task,halted=False)["state"],"RESERVED")
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM council_review_audit_v1").fetchone()[0],0)
        self.assertEqual(self.history()["attempts"][0]["audit_state"],"RESERVED_NO_REPORT")

    def test_ledger_write_failure_rolls_back_audit_insert(self):
        with CouncilAttemptStore(self.db) as store:
            store.db.execute("""CREATE TRIGGER fail_complete BEFORE UPDATE ON council_attempts_v1
                WHEN NEW.payload LIKE '%"outcome":"NEEDS_EVIDENCE"%'
                BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_review()
        with CouncilAttemptStore(self.db) as store:
            self.assertEqual(store.status(self.task,halted=False)["state"],"RESERVED")
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM council_review_audit_v1").fetchone()[0],0)

    def test_deleted_or_modified_audit_fails_closed(self):
        self.run_review()
        with CouncilAttemptStore(self.db) as store:
            original=store.db.execute("SELECT payload,digest FROM council_review_audit_v1").fetchone()
            store.db.execute("UPDATE council_review_audit_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.status(self.task,halted=False)
            store.db.execute("UPDATE council_review_audit_v1 SET payload=?,digest=?",original)
            store.db.execute("DELETE FROM council_review_audit_v1")
            with self.assertRaises(ValueError):
                store.audit_history(self.task,halted=False)

    def test_recomputed_audit_digest_cannot_replace_linked_snapshot(self):
        self.run_review()
        with CouncilAttemptStore(self.db) as store:
            raw=json.loads(store.db.execute("SELECT payload FROM council_review_audit_v1").fetchone()[0])
            raw["snapshot"]["modeled_expected_net"]="999.00"
            raw["snapshot"]["snapshot_sha256"]=_digest(_json(
                {k:v for k,v in raw["snapshot"].items() if k!="snapshot_sha256"}))
            payload=_json(raw)
            store.db.execute("UPDATE council_review_audit_v1 SET payload=?,digest=?",(payload,_digest(payload)))
            with self.assertRaises(ValueError):
                store.audit_history(self.task,halted=False)

    def test_legacy_digest_only_not_fabricated(self):
        from nexus_exchange.agent_handoff import parse_handoff
        h=parse_handoff(dict(task_id="LEGACY.1",from_role="Scout",to_role="Council",
            objective="Synthetic",acceptance_criteria=["source"],source_references=["synthetic"],
            constraints=["offline"],attempt=1))
        with CouncilAttemptStore(self.db) as store:
            store.register(h,now=NOW,halted=False)
            ticket=store.reserve(h,now=NOW,halted=False)
            store.complete(ticket,"RETRY","a"*64,now=NOW,halted=False)
            history=store.audit_history("LEGACY.1",halted=False)
            row=history["attempts"][0]
            self.assertEqual(row["audit_state"],"LEGACY_DIGEST_ONLY")
            self.assertIsNone(row["audit"])
            self.assertFalse(history["current_decision"])

    def test_interrupted_reservation_has_no_fabricated_audit(self):
        with patch("nexus_exchange.council_coordinator.review_criteria",side_effect=RuntimeError("synthetic")):
            with self.assertRaises(RuntimeError):
                self.run_review()
        with CouncilAttemptStore(self.db) as store:
            store.recover_interrupted(self.task,now=NOW,exclusive_owner=True,halted=False)
        row=self.history()["attempts"][0]
        self.assertEqual(row["audit_state"],"INTERRUPTED_NO_REPORT")
        self.assertIsNone(row["audit"])

    def test_snapshot_validation_rejects_extra_data_and_false_claims(self):
        original=self.council.inspect(self.key)
        validate_snapshot(original)
        for changes in ({"external_authority":True},{"reference_ids":{}},
            {"private_path":str(self.file)},{"referenced":17},{"independently_verified_count":1},
            {"reasons":["raw /private/file"]},{"task_id":"COUNCIL."+"a"*64}):
            malformed=dict(original,**changes)
            malformed["snapshot_sha256"]=_digest(_json(
                {k:v for k,v in malformed.items() if k!="snapshot_sha256"}))
            with self.assertRaises(ValueError):
                validate_snapshot(malformed)

    def test_halt_blocks_history_and_review(self):
        self.run_review()
        for value in (True,None,0):
            self.halted=value
            with self.assertRaises(PermissionError):
                self.history()
            with self.assertRaises(PermissionError):
                self.run_review()

    def test_no_downgrade_after_audited_completion(self):
        self.run_review()
        self.now+=timedelta(seconds=1)
        with self.council._snapshot(self.key) as (_snapshot,task,_artifacts):
            from nexus_exchange.council_coordinator import _prepare
            handoff,_=_prepare(task,2)
            with CouncilAttemptStore(self.db) as store:
                ticket=store.reserve(handoff,now=self.now,halted=False)
                with self.assertRaises(ValueError):
                    store.complete(ticket,"RETRY","b"*64,now=self.now,halted=False)
                self.assertEqual(store.status(self.task,halted=False)["state"],"RESERVED")

    def test_legacy_task_upgrades_without_inventing_prior_snapshot(self):
        from nexus_exchange.council_coordinator import CouncilCoordinator
        with self.council._snapshot(self.key) as (_snapshot,task,artifacts):
            with CouncilAttemptStore(self.db) as store:
                legacy=CouncilCoordinator(store,halt_check=lambda:False,clock=lambda:self.now)
                first=legacy.run_once(task,artifacts)
                self.assertEqual(first["ledger"]["attempts_used"],1)
                encoded=store.db.execute("SELECT payload FROM council_attempts_v1").fetchone()[0]
                self.assertEqual(json.loads(encoded)["version"],1)
        self.now+=timedelta(seconds=1)
        self.run_review()
        history=self.history()
        self.assertEqual([row["audit_state"] for row in history["attempts"]],
                         ["LEGACY_DIGEST_ONLY","RECORDED"])
        self.assertIsNone(history["attempts"][0]["audit"])
        with CouncilAttemptStore(self.db) as store:
            encoded=store.db.execute("SELECT payload FROM council_attempts_v1").fetchone()[0]
            self.assertEqual(json.loads(encoded)["version"],2)

    def test_exact_audit_replay_is_idempotent_and_changed_snapshot_rejected(self):
        result=self.run_review()
        entry=result["ledger"]["attempts"][0]
        ticket=dict(task_id=self.task,attempt=entry["attempt"],reservation_id=entry["reservation_id"])
        self.now+=timedelta(seconds=1)
        with CouncilAttemptStore(self.db) as store:
            replay=store.complete(ticket,result["review"]["status"],result["report_sha256"],
                now=self.now,halted=False,audit_snapshot=result["snapshot"],review_report=result["review"])
            self.assertEqual(replay,result["ledger"])
            changed=dict(result["snapshot"],modeled_expected_net="999.00")
            changed["snapshot_sha256"]=_digest(_json(
                {k:v for k,v in changed.items() if k!="snapshot_sha256"}))
            with self.assertRaises(ValueError):
                store.complete(ticket,result["review"]["status"],result["report_sha256"],
                    now=self.now,halted=False,audit_snapshot=changed,review_report=result["review"])
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM council_review_audit_v1").fetchone()[0],1)

    def test_orphaned_audit_for_unreserved_attempt_is_rejected(self):
        self.run_review()
        with CouncilAttemptStore(self.db) as store:
            payload,digest=store.db.execute("SELECT payload,digest FROM council_review_audit_v1").fetchone()
            store.db.execute("INSERT INTO council_review_audit_v1 VALUES (?,?,?,?)",
                             (self.task,2,payload,digest))
            with self.assertRaises(ValueError):
                store.status(self.task,halted=False)
