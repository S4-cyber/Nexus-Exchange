import json
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta

import test_deliverable_files as files
from nexus_exchange.deliverable_files import preview_pins
from nexus_exchange.deliverable_obligations import ObligationStore,NOTE_KINDS,MAX_NOTES
from nexus_exchange.owner_profile import ProfileStore
from test_owner_profile import profile


class ObligationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=files.DeliverableFilesTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.directory=self.fixture.directory
        self.plan=self.fixture.fixture.key
        self.source=self.fixture.source
        self.artifact=self.fixture.dest
        self.db=self.directory/"operator-obligations.sqlite3"
        self.evidence=self.directory/"synthetic-acceptance.txt"
        self.evidence.write_bytes(b"synthetic evidence; not buyer approval")
        self.inputs=dict(source_path=self.source,columns=["id","name","category"],
                         key_column="id",expected_rows=2)
        self.preview=self.fixture.preview()
        self.fixture.workspace.export(self.artifact,confirmed=True)
        self.pins=preview_pins(self.preview)

    def register(self,**changes):
        args=dict(self.inputs,artifact_path=self.artifact,**self.pins)
        args.update(changes)
        return self.guard.csv_file_action("register",self.plan,confirmed=True,**args)

    def history(self,record):
        return self.guard.csv_obligation_action("history",self.plan,obligation_id=record["obligation_id"])

    def note(self,record,**changes):
        args=dict(obligation_id=record["obligation_id"],expected_head=record["head_sha256"],
                  kind="acceptance_claim_noted",evidence_path=self.evidence)
        args.update(changes)
        return self.guard.csv_obligation_action("note",self.plan,confirmed=True,**args)

    def test_registration_and_idempotent_reopen(self):
        record=self.register()
        self.assertEqual(record["state"],"LOCAL_ARTIFACT_RECORDED")
        self.assertEqual(record["binding"]["qa_report"],self.preview["report"])
        self.assertEqual(record,self.register())
        self.assertEqual(record,self.history(record))
        self.assertTrue(record["historical_only"])
        for flag in ("buyer_accepted","contract_awarded","invoice_eligible",
                     "revenue_realized","external_authority","payment_received"):
            self.assertIs(record[flag],False)
        self.assertNotIn(str(self.source),repr(record))
        self.assertNotIn(str(self.artifact),repr(record))

    def test_artifact_or_preview_mismatch_denied_before_store(self):
        self.artifact.write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            self.register()
        self.assertFalse(self.db.exists())
        self.artifact.write_bytes(self.preview["artifact"])
        with self.assertRaises(ValueError):
            self.register(expected_report="0"*64)
        self.assertFalse(self.db.exists())

    def test_source_changed_after_preview_denied(self):
        self.source.write_bytes(b"name,id,category\nGamma,001,Design\nBeta,002,Research\n")
        with self.assertRaises(ValueError):
            self.register()
        self.assertFalse(self.db.exists())

    def test_evidence_note_exact_scope_and_all_false(self):
        first=self.register()
        current=self.note(first)
        self.assertEqual(current["state"],"LOCAL_EVIDENCE_NOTED")
        event=current["notes"][0]
        self.assertEqual(event["previous_sha256"],first["head_sha256"])
        self.assertEqual(event["event_sha256"],current["head_sha256"])
        self.assertEqual(event["kind"],"acceptance_claim_noted")
        self.assertFalse(current["buyer_accepted"])
        self.assertFalse(current["invoice_eligible"])
        self.assertFalse(current["evidence_authenticity_verified"])
        self.assertNotIn(str(self.evidence),repr(current))
        self.assertNotIn("synthetic evidence;",repr(current))
        self.assertEqual(self.history(first),current)

    def test_stale_head_and_duplicate_evidence(self):
        first=self.register()
        current=self.note(first)
        with patch("nexus_exchange.evidence.fingerprint") as reader:
            with self.assertRaises(ValueError):
                self.note(first)
            reader.assert_not_called()
        with self.assertRaises(ValueError):
            self.note(current,kind="rejection_claim_noted")
        self.evidence.write_bytes(b"new synthetic revision request")
        latest=self.note(current,kind="revision_request_noted")
        self.assertEqual([row["kind"] for row in latest["notes"]],
                         ["acceptance_claim_noted","revision_request_noted"])
        self.assertFalse(latest["buyer_accepted"])

    def test_history_and_notes_stay_historical_after_profile_drift(self):
        record=self.register()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.history(record),record)
        result=self.note(record)
        self.assertTrue(result["historical_only"])
        self.assertFalse(result["execution_eligible"])

    def test_list_and_exact_plan_scope(self):
        self.assertEqual(self.guard.csv_obligation_action("list",self.plan,limit=1)["rows"],[])
        self.assertFalse(self.db.exists())
        record=self.register()
        self.assertEqual(self.guard.csv_obligation_action("list",self.plan,limit=1)["rows"],[record])
        with self.assertRaises(ValueError):
            self.guard.csv_obligation_action("history","0"*64,obligation_id=record["obligation_id"])
        self.assertEqual(self.guard.csv_obligation_action("list","0"*64,limit=1)["rows"],[])

    def test_halt_confirmation_and_unknown_operation(self):
        record=self.register()
        with self.assertRaises(PermissionError):
            self.guard.csv_obligation_action("note",self.plan,confirmed=False,
                obligation_id=record["obligation_id"],expected_head=record["head_sha256"],
                kind=NOTE_KINDS[0],evidence_path=self.evidence)
        with self.assertRaises(ValueError):
            self.guard.csv_obligation_action("accept",self.plan)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.history(record)
        with self.assertRaises(PermissionError):
            self.note(record)

    def test_tampered_storage_rejected(self):
        record=self.register()
        current=self.note(record)
        with ObligationStore(self.db,existing_only=True) as store:
            store.db.execute("UPDATE csv_obligation_notes_v1 SET payload='{}'")
        with self.assertRaises(ValueError):
            self.history(current)

    def test_rollback_on_halt_and_cap(self):
        record=self.register()
        from nexus_exchange.evidence import fingerprint
        ref=fingerprint(self.evidence,halted=False)
        now=self.fixture.fixture.now
        with ObligationStore(self.db,existing_only=True) as store:
            with patch("nexus_exchange.deliverable_obligations.MAX_NOTES",0):
                with self.assertRaises(ValueError):
                    store.note(self.plan,record["obligation_id"],kind=NOTE_KINDS[0],
                        reference=ref,expected_head=record["head_sha256"],now=now,
                        confirmed=True,halted=False)
            states=iter([False,False,True])
            with self.assertRaises(PermissionError):
                store.note(self.plan,record["obligation_id"],kind=NOTE_KINDS[0],
                    reference=ref,expected_head=record["head_sha256"],now=now,
                    confirmed=True,halted=False,halt_check=lambda:next(states,True))
        self.assertEqual(self.history(record),record)

    def test_clock_regression_cannot_append(self):
        record=self.register()
        self.fixture.fixture.now+=timedelta(seconds=1)
        current=self.note(record)
        self.fixture.fixture.now-=timedelta(seconds=1)
        self.evidence.write_bytes(b"new")
        with self.assertRaises(ValueError):
            self.note(current)

if __name__=="__main__":
    unittest.main()
