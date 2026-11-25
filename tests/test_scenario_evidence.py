import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from nexus_exchange.checklist_store import context_for
from nexus_exchange.scenario_store import ScenarioStore
from nexus_exchange.scenario_evidence import ScenarioEvidenceStore, ASSUMPTION_FIELDS
from test_cash_feasibility import scenario
from test_schedule_feasibility import plan
from test_lead_store import NOW, reports
from test_owner_profile import profile


class ScenarioEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=Path(tmp.name)
        self.db=self.directory/"scout.sqlite3"
        self.file=self.directory/"synthetic-private-name.txt"
        self.file.write_bytes(b"synthetic terms fixture")
        self.profile=profile()
        self.now=NOW
        self.report=reports()[0]
        with ScenarioStore(self.db) as store:
            store.record(self.report,now=NOW,halted=False)
            lead=store.browse(now=NOW,profile=self.profile,source="sam",halted=False)["leads"][0]
            self.context=context_for(lead)
            self.key=store.save(self.context,scenario(),plan(),profile=self.profile,now=NOW,halted=False)

    def attach(self,store,field="compensation",path=None,**kw):
        args=dict(profile=self.profile,now=self.now,halted=False)
        args.update(kw)
        return store.attach(self.key,field,self.file if path is None else path,**args)

    def coverage(self,store,key=None,**kw):
        args=dict(profile=self.profile,now=self.now,halted=False)
        args.update(kw)
        return store.coverage(self.key if key is None else key,**args)

    def verify(self,store,key,field="compensation",**kw):
        args=dict(profile=self.profile,now=self.now,halted=False)
        args.update(kw)
        return store.verify_attachment(self.key,field,key,self.file,**args)

    def test_all_fields_initially_unverified(self):
        with ScenarioEvidenceStore(self.db) as store:
            result=self.coverage(store)
            self.assertEqual(result["total"],17)
            self.assertEqual(set(ASSUMPTION_FIELDS),{item["field"] for item in result["fields"]})
            self.assertEqual(result["referenced"],0)
            self.assertEqual(result["independently_verified_count"],0)
            self.assertFalse(result["execution_eligible"])

    def test_attach_reopen_and_privacy(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
        with ScenarioEvidenceStore(self.db) as store:
            result=self.coverage(store)
            field=next(f for f in result["fields"] if f["field"]=="compensation")
            ref=field["references"][0]
            self.assertEqual(ref["evidence_id"],key)
            self.assertEqual(field["state"],"REFERENCE_NOTED_UNVERIFIED")
            self.assertEqual(result["referenced"],1)
            self.assertEqual(result["independently_verified_count"],0)
            self.assertFalse(ref["independently_verified"])
            self.assertNotIn(str(self.file),json.dumps(result))
            self.assertNotIn(self.file.name,json.dumps(result))
            self.assertNotIn("synthetic terms fixture",json.dumps(result))

    def test_identical_bytes_replay_same_field_but_not_other_field(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            self.now+=timedelta(seconds=1)
            copy_path=self.directory/"duplicate.txt"
            copy_path.write_bytes(self.file.read_bytes())
            self.assertEqual(self.attach(store,path=copy_path),key)
            different=self.attach(store,"cost:software")
            self.assertNotEqual(different,key)
            self.assertEqual(self.coverage(store)["referenced"],2)

    def test_verify_match_then_mismatch_never_persists_verdict(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            self.assertTrue(self.verify(store,key)["byte_match"])
            self.file.write_bytes(b"changed")
            result=self.verify(store,key)
            self.assertFalse(result["byte_match"])
            self.assertFalse(result["independently_verified"])
            self.assertFalse(result["external_authority"])
            self.assertEqual(self.coverage(store)["independently_verified_count"],0)
            self.assertNotIn("byte_match",self.coverage(store)["fields"][0]["references"][0])

    def test_wrong_assumption_and_foreign_scenario_rejected_before_read(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            other=store.save(self.context,scenario(compensation="201"),plan(),
                             profile=self.profile,now=NOW,halted=False)
            with patch("nexus_exchange.scenario_evidence.verify_reference") as read:
                with self.assertRaises(ValueError):
                    self.verify(store,key,field="cost:software")
                with self.assertRaises(ValueError):
                    store.verify_attachment(other,"compensation",key,self.file,
                        profile=self.profile,now=NOW,halted=False)
                read.assert_not_called()
            self.assertEqual(self.coverage(store,other)["referenced"],0)

    def test_unknown_and_invalid_fields_never_read_file(self):
        with ScenarioEvidenceStore(self.db) as store:
            self.key=store.save(self.context,scenario(compensation=None),plan(),
                profile=self.profile,now=NOW,halted=False)
            with patch("nexus_exchange.scenario_evidence.fingerprint") as read:
                for field in ("compensation","currency","cost:invented",True):
                    with self.assertRaises(ValueError):
                        self.attach(store,field)
                read.assert_not_called()
            row=next(f for f in self.coverage(store)["fields"] if f["field"]=="compensation")
            self.assertEqual(row["state"],"ASSUMPTION_UNKNOWN")

    def test_halt_precedes_io_and_prevents_commit(self):
        with ScenarioEvidenceStore(self.db) as store:
            with patch("nexus_exchange.scenario_evidence.fingerprint") as read:
                for halted in (None,True,0):
                    with self.assertRaises(PermissionError):
                        self.attach(store,halted=halted)
                    with self.assertRaises(PermissionError):
                        self.coverage(store,halted=halted)
                read.assert_not_called()
            from nexus_exchange.evidence import fingerprint
            flag=[False]
            def interrupted(path,**kwargs):
                result=fingerprint(path,**kwargs)
                flag[0]=True
                return result
            with patch("nexus_exchange.scenario_evidence.fingerprint",side_effect=interrupted):
                with self.assertRaises(PermissionError):
                    self.attach(store,halt_check=lambda:flag[0])
            self.assertEqual(self.coverage(store)["referenced"],0)
            self.assertFalse(store.db.in_transaction)

    def test_profile_and_observation_supersession(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            with self.assertRaises(ValueError):
                self.coverage(store,profile=profile(hours_per_week=30))
            later=NOW+timedelta(minutes=1)
            updated=copy.deepcopy(self.report)
            updated["leads"][0]["retrieved_at"]=later.isoformat()
            store.record(updated,now=later,halted=False)
            self.now=later
            with patch("nexus_exchange.scenario_evidence.verify_reference") as read:
                with self.assertRaises(ValueError):
                    self.verify(store,key)
                read.assert_not_called()
            with self.assertRaises(ValueError):
                self.coverage(store)

    def test_context_change_during_hash_rejected(self):
        from nexus_exchange.evidence import fingerprint
        with ScenarioEvidenceStore(self.db) as store:
            def changed(path,**kwargs):
                result=fingerprint(path,**kwargs)
                updated=copy.deepcopy(self.report)
                later=NOW+timedelta(minutes=1)
                updated["leads"][0]["retrieved_at"]=later.isoformat()
                with ScenarioStore(self.db) as other:
                    other.record(updated,now=later,halted=False)
                return result
            with patch("nexus_exchange.scenario_evidence.fingerprint",side_effect=changed):
                with self.assertRaises(ValueError):
                    self.attach(store)
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM scout_assumption_evidence_v1").fetchone()[0],0)

    def test_bounded_reference_capacity_and_replay(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            with patch("nexus_exchange.scenario_evidence.MAX_REFERENCES_PER_FIELD",1):
                self.assertEqual(self.attach(store),key)
                self.file.write_bytes(b"another")
                with self.assertRaisesRegex(ValueError,"capacity"):
                    self.attach(store)
            with patch("nexus_exchange.scenario_evidence.MAX_EVIDENCE_ROWS",1):
                with self.assertRaisesRegex(ValueError,"capacity"):
                    self.attach(store,"cost:software")
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(self.coverage(store)["referenced"],1)

    def test_tamper_with_recomputed_digest_still_fails_identity(self):
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            encoded=store.db.execute("SELECT payload FROM scout_assumption_evidence_v1 WHERE evidence_id=?",(key,)).fetchone()[0]
            raw=json.loads(encoded)
            raw["reference"]="sha256:"+"a"*64+";bytes:1"
            changed=json.dumps(raw,sort_keys=True,separators=(",",":"),ensure_ascii=True)
            store.db.execute("UPDATE scout_assumption_evidence_v1 SET payload=?,digest=? WHERE evidence_id=?",
                (changed,hashlib.sha256(changed.encode("ascii")).hexdigest(),key))
            with self.assertRaises(ValueError):
                self.coverage(store)
            self.assertFalse(store.db.in_transaction)

    def test_failed_insert_rollback_and_backward_clock(self):
        with ScenarioEvidenceStore(self.db) as store:
            store.db.execute("""CREATE TRIGGER fail_evidence BEFORE INSERT ON scout_assumption_evidence_v1
                BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
            with self.assertRaises(sqlite3.IntegrityError):
                self.attach(store)
            self.assertFalse(store.db.in_transaction)
            self.assertEqual(self.coverage(store)["referenced"],0)
            store.db.execute("DROP TRIGGER fail_evidence")
            self.now=NOW+timedelta(minutes=1)
            key=self.attach(store)
            self.now=NOW
            with self.assertRaises(ValueError):
                self.verify(store,key)
            with self.assertRaises(ValueError):
                self.coverage(store)

    def test_complete_reference_coverage_is_not_factual_verification(self):
        with ScenarioEvidenceStore(self.db) as store:
            for field in ASSUMPTION_FIELDS:
                self.attach(store,field)
            report=self.coverage(store)
            self.assertEqual(report["referenced"],17)
            self.assertEqual(report["independently_verified_count"],0)
            for flag in ("independently_verified","genesis_verified","execution_eligible","external_authority"):
                self.assertIs(report[flag],False)
            self.assertTrue(all(f["state"]=="REFERENCE_NOTED_UNVERIFIED" for f in report["fields"]))

    def test_cross_connection_replay_and_no_private_payload(self):
        with ScenarioEvidenceStore(self.db) as first, ScenarioEvidenceStore(self.db) as second:
            key=self.attach(first)
            self.assertEqual(self.attach(second),key)
            rows=second.db.execute("SELECT payload FROM scout_assumption_evidence_v1").fetchall()
            self.assertEqual(len(rows),1)
            for private in (str(self.file),self.file.name,"synthetic terms fixture"):
                self.assertNotIn(private,rows[0][0])

    def test_supersession_during_recheck_blocks_return(self):
        from nexus_exchange.evidence import verify_reference
        with ScenarioEvidenceStore(self.db) as store:
            key=self.attach(store)
            def changed(path,reference,**kwargs):
                result=verify_reference(path,reference,**kwargs)
                later=NOW+timedelta(seconds=1)
                updated=copy.deepcopy(self.report)
                updated["leads"][0]["retrieved_at"]=later.isoformat()
                with ScenarioStore(self.db) as other:
                    other.record(updated,now=later,halted=False)
                return result
            with patch("nexus_exchange.scenario_evidence.verify_reference",side_effect=changed):
                with self.assertRaises(ValueError):
                    self.verify(store,key)
            self.assertFalse(store.db.in_transaction)
