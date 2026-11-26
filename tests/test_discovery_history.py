import copy
import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock,patch

from nexus_exchange import sam_search
from nexus_exchange.lead_store import LeadStore, _json, _digest
from nexus_exchange.scout_discovery import build_plan,resolve_query
from nexus_exchange.discovery_history import recent_hint,hint_text
from nexus_exchange.operator_capabilities import CSV_ID,JSON_ID
from test_scout_discovery import NOW,profile
import test_sam_search as sam


class SearchHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"scout-leads.sqlite3"
        self.profile=profile(sources=["sam","ted","uk_tender","uk_contracts","canada"])
        self.plan=build_plan(self.profile,CSV_ID,now=NOW,halted=False)
        self.row=next(r for r in self.plan["options"] if r["source"]=="sam" and r["procurement_type"]=="k")
        _,q=resolve_query(self.plan,self.row["option_id"],self.profile,now=NOW,halted=False)
        self.report=sam_search.search(q,sam.KEY,approved=True,halt_check=lambda:False,
            clock=lambda:NOW,transport=Mock(return_value=(200,sam.page([sam.notice()]))))
        self.ctx=dict(plan=self.plan,option_id=self.row["option_id"],profile=self.profile,
                      started_at=NOW,task_id="1"*32)

    def record(self,store,report=None,context=None,**kwargs):
        return store.record(self.report if report is None else report,now=NOW,halted=False,
                            discovery=self.ctx if context is None else context,**kwargs)

    def test_receipt_and_observation_reopen_without_credentials(self):
        with LeadStore(self.path) as store:
            self.assertEqual(self.record(store),1)
        with LeadStore(self.path) as store:
            history=store.search_history(now=NOW,halted=False)
            self.assertEqual(history["total"],1)
            row=history["rows"][0]
            self.assertEqual((row["requests"],row["returned"],row["inserted"]),(1,1,1))
            self.assertEqual(row["scope"]["source"],"sam")
            self.assertEqual(row["scope"]["filter_value"],"csv sorting")
            self.assertFalse(row["external_authority"])
            self.assertTrue(row["historical_only"])
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],1)
            self.assertNotIn(sam.KEY,_json(history))
            self.assertNotIn("unrelated private preference",_json(history))
            hint=recent_hint(self.row,history,now=NOW)
            self.assertEqual(hint["match"],"EXACT_QUERY")
            self.assertFalse(hint["automatic_skip"])
            self.assertIn("may still confirm",hint_text(hint))

    def test_history_snapshot_survives_concurrent_archive_change(self):
        import sqlite3
        from nexus_exchange.discovery_history import _verify_archive
        with LeadStore(self.path) as store:
            self.record(store)
            self.assertEqual(store.db.execute("PRAGMA journal_mode=WAL").fetchone()[0],"wal")
            writer=sqlite3.connect(self.path,timeout=1)
            try:
                def change_after_receipt_read(db,payload,cache):
                    self.assertTrue(db.in_transaction)
                    with writer:
                        writer.execute("DELETE FROM scout_observations_v1")
                    return _verify_archive(db,payload,cache)
                with patch("nexus_exchange.discovery_history._verify_archive",
                           side_effect=change_after_receipt_read):
                    history=store.search_history(now=NOW,halted=False)
                self.assertTrue(history["rows"][0]["local_archive_consistent"])
                self.assertFalse(store.db.in_transaction)
                with self.assertRaisesRegex(ValueError,"missing from archive"):
                    store.search_history(now=NOW,halted=False)
                self.assertFalse(store.db.in_transaction)
            finally:
                writer.close()

    def test_history_capacity_and_hidden_receipt_integrity(self):
        with LeadStore(self.path) as store:
            self.record(store)
            self.record(store,context=dict(self.ctx,task_id="2"*32))
            with patch("nexus_exchange.discovery_history.MAX_RECEIPTS",1):
                with self.assertRaisesRegex(ValueError,"exceeds bound"):
                    store.search_history(now=NOW,limit=1,halted=False)
            self.assertFalse(store.db.in_transaction)
            store.db.execute("UPDATE scout_search_receipts_v1 SET payload='{}' WHERE task_id=?",
                             ("2"*32,))
            with self.assertRaisesRegex(ValueError,"digest mismatch"):
                store.search_history(now=NOW,limit=1,halted=False)
            self.assertFalse(store.db.in_transaction)

    def test_history_does_not_rollback_callers_transaction(self):
        with LeadStore(self.path) as store:
            self.record(store)
            store.db.execute("BEGIN IMMEDIATE")
            try:
                with self.assertRaisesRegex(ValueError,"idle archive connection"):
                    store.search_history(now=NOW,halted=False)
                self.assertTrue(store.db.in_transaction)
            finally:
                store.db.rollback()
            self.assertEqual(store.search_history(now=NOW,halted=False)["total"],1)

    def test_exact_refs_and_missing_archive_denied(self):
        with LeadStore(self.path) as store:
            self.record(store)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            self.assertTrue(row["local_archive_consistent"])
            self.assertEqual(len(row["observation_refs"]),1)
            self.assertEqual(row["observations_sha256"],_digest(_json(row["observation_refs"])))
            store.db.execute("DELETE FROM scout_observations_v1")
            with self.assertRaisesRegex(ValueError,"missing from archive"):
                store.search_history(now=NOW,halted=False)

    def test_resealed_reference_digest_mismatch_denied(self):
        with LeadStore(self.path) as store:
            self.record(store)
            raw,=store.db.execute("SELECT payload FROM scout_search_receipts_v1").fetchone()
            value=json.loads(raw)
            value["observation_refs"][0][3]="f"*64
            value["observations_sha256"]=_digest(_json(value["observation_refs"]))
            encoded=_json(value)
            store.db.execute("UPDATE scout_search_receipts_v1 SET payload=?,payload_sha256=?",
                             (encoded,_digest(encoded)))
            with self.assertRaisesRegex(ValueError,"archive digest mismatch"):
                store.search_history(now=NOW,halted=False)

    def test_legacy_receipt_is_readable_but_not_verified(self):
        with LeadStore(self.path) as store:
            self.record(store)
            raw,=store.db.execute("SELECT payload FROM scout_search_receipts_v1").fetchone()
            value=json.loads(raw)
            value["format"]="nexus-scout-search-receipt-v1"
            value.pop("observation_refs")
            encoded=_json(value)
            store.db.execute("UPDATE scout_search_receipts_v1 SET payload=?,payload_sha256=?",
                             (encoded,_digest(encoded)))
            history=store.search_history(now=NOW,halted=False)
            self.assertFalse(history["rows"][0]["local_archive_consistent"])
            self.assertFalse(recent_hint(self.row,history,now=NOW)["local_archive_consistent"])

    def test_reference_time_and_count_fail_closed(self):
        from nexus_exchange.discovery_history import _validate
        with LeadStore(self.path) as store:
            self.record(store)
            raw,=store.db.execute("SELECT payload FROM scout_search_receipts_v1").fetchone()
        original=json.loads(raw)
        for mutation in ("count","time","duplicate"):
            value=copy.deepcopy(original)
            if mutation=="count":
                value["observation_refs"]=[]
            elif mutation=="time":
                value["observation_refs"][0][2]=(NOW+timedelta(seconds=1)).isoformat(timespec="microseconds")
            else:
                value["observation_refs"]*=2
                value["returned"]=2
            value["observations_sha256"]=_digest(_json(value["observation_refs"]))
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                _validate(value)

    def test_wrong_query_or_source_rolls_back_archive_and_receipt(self):
        report=copy.deepcopy(self.report)
        report["query"]["title"]="unreviewed query"
        with LeadStore(self.path) as store:
            with self.assertRaises(ValueError):
                self.record(store,report)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],0)
            self.assertEqual(store.search_history(now=NOW,halted=False)["total"],0)
            report=copy.deepcopy(self.report)
            report["requests"]=4
            with self.assertRaises(ValueError):
                self.record(store,report)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],0)

    def test_duplicate_task_denied_and_new_search_records_zero_insertions(self):
        with LeadStore(self.path) as store:
            self.record(store)
            with self.assertRaises(Exception) as exc:
                self.record(store)
            import sqlite3
            self.assertIsInstance(exc.exception,sqlite3.IntegrityError)
            self.assertEqual(self.record(store,context=dict(self.ctx,task_id="2"*32)),0)
            history=store.search_history(now=NOW,halted=False)
            self.assertEqual(history["total"],2)
            self.assertEqual(sorted(r["inserted"] for r in history["rows"]),[0,1])
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],1)

    def test_halt_and_receipt_capacity_rollback(self):
        with LeadStore(self.path) as store:
            with self.assertRaises(PermissionError):
                self.record(store,halt_check=lambda:True)
            with patch("nexus_exchange.discovery_history.MAX_RECEIPTS",0):
                with self.assertRaises(ValueError):
                    self.record(store)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],0)
            self.assertEqual(store.search_history(now=NOW,halted=False)["total"],0)

    def test_empty_search_is_recorded_without_claiming_no_opportunity(self):
        _,q=resolve_query(self.plan,self.row["option_id"],self.profile,now=NOW,halted=False)
        report=sam_search.search(q,sam.KEY,approved=True,halt_check=lambda:False,
            clock=lambda:NOW,transport=Mock(return_value=(200,sam.page([]))))
        with LeadStore(self.path) as store:
            self.assertEqual(self.record(store,report),0)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            self.assertEqual(row["returned"],0)
            self.assertFalse(row["actual_opportunity_verified"])

    def test_resealed_invalid_receipt_rejected(self):
        with LeadStore(self.path) as store:
            self.record(store)
            raw,=store.db.execute("SELECT payload FROM scout_search_receipts_v1").fetchone()
            changed=json.loads(raw)
            changed["external_authority"]=True
            encoded=_json(changed)
            store.db.execute("UPDATE scout_search_receipts_v1 SET payload=?,payload_sha256=?",
                             (encoded,_digest(encoded)))
            with self.assertRaises(ValueError):
                store.search_history(now=NOW,halted=False)

    def test_recent_hint_not_cache_or_future_or_other_service_phrase(self):
        with LeadStore(self.path) as store:
            self.record(store)
            history=store.search_history(now=NOW,halted=False)
        different=build_plan(self.profile,JSON_ID,now=NOW,halted=False)
        row=next(r for r in different["options"] if r["source"]=="sam" and r["procurement_type"]=="k")
        self.assertIsNone(recent_hint(row,history,now=NOW))
        self.assertIsNone(recent_hint(self.row,history,now=NOW+timedelta(minutes=16)))
        self.assertIsNone(recent_hint(self.row,history,now=NOW-timedelta(seconds=1)))
        # Sliding UK release windows can overlap across service labels.
        old=next(r for r in self.plan["options"] if r["source"]=="uk_tender")
        newplan=build_plan(self.profile,JSON_ID,now=NOW+timedelta(minutes=1),halted=False)
        new=next(r for r in newplan["options"] if r["source"]=="uk_tender")
        from nexus_exchange.discovery_history import _scope,_filter
        historical=dict(history["rows"][0],scope=_scope(old),filter_sha256=_filter(_scope(old)),
                        truncated=True)
        hint=recent_hint(new,{"rows":[historical]},now=NOW+timedelta(minutes=1))
        self.assertEqual(hint["match"],"OVERLAPPING_WINDOW")
        self.assertTrue(hint["truncated"])
        self.assertFalse(hint["freshness_verified"])


    def test_review_receipt_shows_exact_historical_observation_without_authority(self):
        from nexus_exchange.discovery_history import review_receipt, receipt_review_text
        with LeadStore(self.path) as store:
            self.record(store)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            report=review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=NOW,halted=False)
            self.assertEqual(len(report["observations"]),1)
            item=report["observations"][0]
            self.assertEqual(item["observation_sha256"],row["observation_refs"][0][3])
            self.assertEqual(item["retrieved_at"],row["observation_refs"][0][2])
            self.assertEqual(item["latest_state"],"SAME_OBSERVATION")
            self.assertIn("HISTORICAL_OBSERVATION_REVALIDATION_REQUIRED",item["blockers"])
            self.assertFalse(item["execution_eligible"])
            self.assertFalse(report["external_authority"])
            self.assertIn(item["source_url"],receipt_review_text(report))
            self.assertFalse(store.db.in_transaction)

    def test_review_receipt_distinguishes_later_observation_without_substitution(self):
        from nexus_exchange.discovery_history import review_receipt
        later=NOW+timedelta(seconds=1)
        _,q=resolve_query(self.plan,self.row["option_id"],self.profile,now=NOW,halted=False)
        report=sam_search.search(q,sam.KEY,approved=True,halt_check=lambda:False,
            clock=lambda:later,transport=Mock(return_value=(200,sam.page([sam.notice()]))))
        with LeadStore(self.path) as store:
            self.record(store)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            self.assertEqual(store.record(report,now=later,halted=False),1)
            reviewed=review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=later,halted=False)
            item=reviewed["observations"][0]
            self.assertEqual(item["retrieved_at"],row["observation_refs"][0][2])
            self.assertEqual(item["observation_sha256"],row["observation_refs"][0][3])
            self.assertEqual(item["latest_retrieved_at"],later.isoformat(timespec="microseconds"))
            self.assertEqual(item["latest_state"],"LATER_OBSERVATION_KNOWN")
            self.assertNotEqual(item["latest_observation_sha256"],item["observation_sha256"])
            earlier=review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=NOW,halted=False)
            self.assertEqual(earlier["observations"][0]["latest_state"],"FUTURE_OBSERVATION_KNOWN")

    def test_review_receipt_rechecks_age_and_rejects_future_receipt(self):
        from nexus_exchange.discovery_history import review_receipt
        with LeadStore(self.path) as store:
            self.record(store)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            report=review_receipt(store.db,row["task_id"],row["receipt_sha256"],
                                  now=NOW+timedelta(hours=25),halted=False)
            self.assertIn("OBSERVATION_STALE",report["observations"][0]["blockers"])
            with self.assertRaises(ValueError):
                review_receipt(store.db,row["task_id"],row["receipt_sha256"],
                               now=NOW-timedelta(seconds=1),halted=False)
            self.assertFalse(store.db.in_transaction)

    def test_review_receipt_rejects_changed_selection_missing_evidence_and_halt(self):
        from nexus_exchange.discovery_history import review_receipt
        with LeadStore(self.path) as store:
            self.record(store)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            for halted in (True,None,0):
                with self.assertRaises(PermissionError):
                    review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=NOW,halted=halted)
            for task,digest in (("2"*32,row["receipt_sha256"]),(row["task_id"],"f"*64)):
                with self.assertRaises(ValueError):
                    review_receipt(store.db,task,digest,now=NOW,halted=False)
            store.db.execute("DELETE FROM scout_observations_v1")
            with self.assertRaises(ValueError):
                review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=NOW,halted=False)
            self.assertFalse(store.db.in_transaction)

    def test_review_empty_receipt_does_not_claim_absence_of_opportunity(self):
        from nexus_exchange.discovery_history import review_receipt,receipt_review_text
        _,q=resolve_query(self.plan,self.row["option_id"],self.profile,now=NOW,halted=False)
        report=sam_search.search(q,sam.KEY,approved=True,halt_check=lambda:False,
            clock=lambda:NOW,transport=Mock(return_value=(200,sam.page([]))))
        with LeadStore(self.path) as store:
            self.record(store,report)
            row=store.search_history(now=NOW,halted=False)["rows"][0]
            view=review_receipt(store.db,row["task_id"],row["receipt_sha256"],now=NOW,halted=False)
            self.assertEqual(view["observations"],[])
            self.assertFalse(view["provider_freshness_verified"])
            self.assertIn("not proof",receipt_review_text(view))


if __name__=="__main__":
    unittest.main()
