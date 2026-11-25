import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from nexus_exchange.lead_store import LeadStore, ResultChangedError
from nexus_exchange.checklist_store import context_for
from nexus_exchange.owner_profile import profile_revision
from nexus_exchange import sam_search,ted_search,fts_search,canada_search
import test_sam_search as sam
import test_ted_search as ted
import test_fts_search as fts
import test_canada_search as ca
import test_cf_search as cf
import test_usaspending_search as spending

NOW=sam.NOW
OPTS=dict(approved=True,halt_check=lambda:False,clock=lambda:NOW)

def reports():
    return [
        sam_search.search(sam.QUERY,sam.KEY,transport=Mock(return_value=(200,sam.page([sam.notice()]))),**OPTS),
        ted_search.search(ted.QUERY,transport=Mock(return_value=(200,ted.page([ted.notice()]))),**OPTS),
        fts_search.search(fts.QUERY,transport=Mock(return_value=(200,fts.page([fts.release()]))),**OPTS),
        canada_search.search(ca.QUERY,transport=Mock(return_value=(200,ca.dataset([ca.notice()]),ca.MODIFIED)),**OPTS),
    ]

class LeadStoreTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/"leads.sqlite3"

    def test_four_sources_reopen_filter_and_no_authority(self):
        with LeadStore(self.path) as store:
            for report in reports():
                self.assertEqual(store.record(report,now=NOW,halted=False),1)
        with LeadStore(self.path) as store:
            result=store.browse(now=NOW,halted=False)
            self.assertEqual(result["returned"],4)
            self.assertEqual({r["source"] for r in result["leads"]},{"sam","ted","uk_tender","canada"})
            self.assertTrue(all(not r["research_candidate"] and not r["execution_eligible"]
                and not r["external_authority"] and r["cash_exposure"] is None for r in result["leads"]))
            self.assertTrue(all(len(r["todo"])==7 for r in result["leads"]))
            self.assertEqual(store.browse(now=NOW,source="canada",halted=False)["returned"],1)
            self.assertEqual(store.browse(now=NOW,query="software",halted=False)["returned"],1)
            self.assertEqual(store.browse(now=NOW,limit=2,halted=False)["returned"],2)
            self.assertNotIn(sam.KEY,json.dumps(result))

    def test_replay_and_latest_observation(self):
        report=reports()[0]
        newer=copy.deepcopy(report)
        newer["leads"][0]["retrieved_at"]=(NOW+timedelta(minutes=1)).isoformat()
        newer["leads"][0]["title"]="Revised historical title"
        with LeadStore(self.path) as store:
            self.assertEqual(store.record(report,now=NOW,halted=False),1)
            self.assertEqual(store.record(report,now=NOW,halted=False),0)
            self.assertEqual(store.record(newer,now=NOW+timedelta(minutes=1),halted=False),1)
            self.assertEqual(store.browse(now=NOW+timedelta(minutes=1),halted=False)["leads"][0]["title"],"Revised historical title")

    def test_search_result_resolves_the_same_checklist_as_history_for_every_source(self):
        source_reports = reports() + [
            cf.search(cf.QUERY, transport=Mock(return_value=(200, cf.page([cf.release()]))), **OPTS),
            spending.search(spending.QUERY, transport=Mock(return_value=(200, spending.page([spending.award()]))), **OPTS),
        ]
        profile = dict(mode="genesis", budget="0", hours_per_week=5, sources=["sam"],
                       naics=[], cpv=[], keywords=[])
        with LeadStore(self.path) as store:
            for report in source_reports:
                with self.subTest(fmt=report["format"]):
                    store.record(report, now=NOW, halted=False)
                    result = store.resolve_result(report, 0, now=NOW, profile=profile, halted=False)
                    archived = store.browse(now=NOW, source=result["source"], profile=profile, halted=False)["leads"]
                    self.assertEqual(context_for(result), context_for(archived[0]))
                    self.assertEqual(context_for(result)["profile_revision"], profile_revision(profile))

    def test_selected_row_rejects_missing_changed_and_superseded_results(self):
        report = sam_search.search(sam.QUERY, sam.KEY,
            transport=Mock(return_value=(200, sam.page([sam.notice(1), sam.notice(2)]))), **OPTS)
        with LeadStore(self.path) as store:
            def resolve(report, index):
                return store.resolve_result(report, index, now=NOW+timedelta(minutes=1), halted=False)
            with self.assertRaises(ResultChangedError):
                resolve(report, 1)
            store.record(report, now=NOW, halted=False)
            self.assertEqual(resolve(report, 1)["notice_id"], report["leads"][1]["notice_id"])
            for bad_index in (-1, True, 2):
                with self.subTest(index=bad_index), self.assertRaises(ValueError):
                    resolve(report, bad_index)
            with self.assertRaises(PermissionError):
                store.resolve_result(report, 1, now=NOW, halted=True)
            with self.assertRaises(ResultChangedError):
                resolve(dict(report, page_sha256=["f"*64]), 1)
            revised = copy.deepcopy(report["leads"][1])
            revised["retrieved_at"] = (NOW+timedelta(minutes=1)).isoformat()
            store.record(dict(report, returned=1, leads=[revised]), now=NOW+timedelta(minutes=1), halted=False)
            with self.assertRaises(ResultChangedError):
                resolve(report, 1)
            self.assertEqual(resolve(report, 0)["notice_id"], report["leads"][0]["notice_id"])

    def test_conflict_and_atomic_rollback(self):
        report=reports()[0]
        with LeadStore(self.path) as store:
            store.record(report,now=NOW,halted=False)
            conflicting=copy.deepcopy(report)
            conflicting["leads"][0]["title"]="Conflict"
            extra=copy.deepcopy(report["leads"][0])
            extra["notice_id"]="a"*32
            extra["source_url"]=sam_search.notice_url(extra["notice_id"])
            conflicting["leads"].insert(0,extra)
            conflicting["returned"]=2
            with self.assertRaises(ValueError):
                store.record(conflicting,now=NOW,halted=False)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],1)

    def test_stale_expired_and_date_only(self):
        with LeadStore(self.path) as store:
            for report in reports():
                store.record(report,now=NOW,halted=False)
            result=store.browse(now=NOW+timedelta(days=12),halted=False)
            self.assertTrue(all("OBSERVATION_STALE" in r["blockers"] for r in result["leads"]))
            self.assertTrue(all(any(x.startswith("REPORTED_DEADLINE") for x in r["blockers"]) for r in result["leads"]))

    def test_uk_lifecycle_across_sessions(self):
        older=reports()[2]
        later=fts_search.search(fts.QUERY,transport=Mock(return_value=(200,fts.page([
            fts.release(2,ocid=older["leads"][0]["ocid"],date="2026-11-24T10:00:00Z",
                tag=["award"],tender=None)]))),**OPTS)
        with LeadStore(self.path) as store:
            store.record(older,now=NOW,halted=False)
            store.record(later,now=NOW,halted=False)
            rows=store.browse(now=NOW,halted=False)["leads"]
            self.assertTrue(any("LATER_UK_EVENT_IN_ARCHIVE" in r["blockers"] for r in rows))

    def test_uk_lifecycle_does_not_forget_later_event_on_regressed_retrieval(self):
        older=reports()[2]
        award=fts_search.search(fts.QUERY,transport=Mock(return_value=(200,fts.page([
            fts.release(2,ocid=older["leads"][0]["ocid"],date="2026-11-24T10:00:00Z",
                tag=["award"],tender=None)]))),**OPTS)
        repeated=copy.deepcopy(award)
        repeated["leads"][0]["retrieved_at"]=(NOW+timedelta(minutes=1)).isoformat()
        regressed=copy.deepcopy(award)
        regressed["leads"][0]["retrieved_at"]=(NOW+timedelta(minutes=2)).isoformat()
        regressed["leads"][0]["release_date"]="2026-11-24T08:00:00Z"
        with LeadStore(self.path) as store:
            for report,stamp in ((older,NOW),(award,NOW),(repeated,NOW+timedelta(minutes=1))):
                store.record(report,now=stamp,halted=False)
            rows=store.browse(now=NOW+timedelta(minutes=1),halted=False)["leads"]
            self.assertFalse(any("AMBIGUOUS_UK_EVENT_IN_ARCHIVE" in row["blockers"] for row in rows))
            store.record(regressed,now=NOW+timedelta(minutes=2),halted=False)
            rows=store.browse(now=NOW+timedelta(minutes=2),halted=False)["leads"]
            self.assertEqual(len(rows),2)
            self.assertTrue(all("LATER_UK_EVENT_IN_ARCHIVE" in row["blockers"] for row in rows))
            self.assertTrue(all(row["execution_eligible"] is False for row in rows))

    def test_uk_lifecycle_distinct_release_tie_preserved_across_observations(self):
        first=reports()[2]
        second=fts_search.search(fts.QUERY,transport=Mock(return_value=(200,fts.page([
            fts.release(2,ocid=first["leads"][0]["ocid"])]))),**OPTS)
        changed=copy.deepcopy(second)
        changed["leads"][0]["retrieved_at"]=(NOW+timedelta(minutes=1)).isoformat()
        changed["leads"][0]["release_date"]="2026-11-24T08:00:00Z"
        with LeadStore(self.path) as store:
            for report,stamp in ((first,NOW),(second,NOW),(changed,NOW+timedelta(minutes=1))):
                store.record(report,now=stamp,halted=False)
            rows=store.browse(now=NOW+timedelta(minutes=1),halted=False)["leads"]
            by_id={row["notice_id"]:row for row in rows}
            self.assertIn("AMBIGUOUS_UK_EVENT_IN_ARCHIVE",by_id[first["leads"][0]["notice_id"]]["blockers"])
            self.assertIn("LATER_UK_EVENT_IN_ARCHIVE",by_id[second["leads"][0]["notice_id"]]["blockers"])

    def test_archive_capacity_and_integrity_checked_before_filtering(self):
        with LeadStore(self.path) as store:
            for report in reports()[:2]:
                store.record(report,now=NOW,halted=False)
            with patch("nexus_exchange.lead_store.MAX_ROWS",2):
                self.assertEqual(store.browse(now=NOW,source="sam",halted=False)["returned"],1)
            with patch("nexus_exchange.lead_store.MAX_ROWS",1):
                with self.assertRaisesRegex(ValueError,"archive exceeds"):
                    store.browse(now=NOW,source="sam",halted=False)
            store.db.execute("UPDATE scout_observations_v1 SET payload='{}' WHERE source='ted'")
            with self.assertRaisesRegex(ValueError,"integrity mismatch"):
                store.browse(now=NOW,source="sam",halted=False)

    def test_unsafe_authority_future_and_link_rejected(self):
        report=reports()[0]
        with LeadStore(self.path) as store:
            for key,value in (("execution_eligible",True),("external_authority",True),
                ("cash_exposure","0"),("source_url","https://evil.example"),
                ("retrieved_at",(NOW+timedelta(days=1)).isoformat())):
                bad=copy.deepcopy(report)
                bad["leads"][0][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):
                    store.record(bad,now=NOW,halted=False)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],0)

    def test_tamper_detection(self):
        with LeadStore(self.path) as store:
            store.record(reports()[0],now=NOW,halted=False)
            store.db.execute("UPDATE scout_observations_v1 SET payload='{}'")
            with self.assertRaises(ValueError):
                store.browse(now=NOW,halted=False)

    def test_cap_and_halt(self):
        report=reports()[0]
        with LeadStore(self.path) as store:
            for state in (True,None,0):
                with self.assertRaises(PermissionError):
                    store.record(report,now=NOW,halted=state)
                with self.assertRaises(PermissionError):
                    store.browse(now=NOW,halted=state)
            with patch("nexus_exchange.lead_store.MAX_ROWS",0):
                with self.assertRaises(ValueError):
                    store.record(report,now=NOW,halted=False)
            self.assertEqual(store.browse(now=NOW,halted=False)["returned"],0)

    def test_desktop_worker_journal_integration(self):
        from desktop import run_logged
        from nexus_exchange.event_store import EventStore
        from threading import Event
        report=reports()[0]
        events=EventStore(":memory:")
        try:
            with LeadStore(self.path) as store:
                result=run_logged(events,work=lambda **kw:report,target="Scout research",lead_store=store)
                self.assertEqual(result,report)
                self.assertEqual(events.read()[-1]["state"],"succeeded")
                self.assertEqual(store.browse(now=NOW,halted=False)["returned"],1)
                stop=Event()
                stop.set()
                self.assertEqual(run_logged(events,stop,work=lambda **kw:report,
                    target="Scout research",lead_store=store),())
                self.assertEqual(events.read()[-1]["state"],"cancelled")
        finally:
            events.close()
