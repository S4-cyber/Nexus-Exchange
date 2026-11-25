import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock
from nexus_exchange.owner_profile import (ProfileChangedError,ProfileStore,normalize_profile,profile_revision,
    assess_profile,reported_codes)
from nexus_exchange.lead_store import LeadStore
from test_lead_store import reports,NOW,OPTS
from nexus_exchange import usaspending_search
import test_usaspending_search as spending

def profile(**changes):
    raw=dict(mode="genesis",budget="0",hours_per_week=20,
        sources=["sam","ted","uk_tender","canada","usaspending"],
        naics=["541519"],cpv=["72"],keywords=["software","digital services"])
    raw.update(changes)
    return raw

class ProfileTests(unittest.TestCase):
    def test_profile_roundtrip_clear_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"owner.sqlite3"
            with ProfileStore(path) as store:
                self.assertIsNone(store.load(halted=False))
                revision=store.save(profile(),halted=False)
                self.assertEqual(revision,profile_revision(profile()))
            with ProfileStore(path) as store:
                self.assertEqual(store.load(halted=False),normalize_profile(profile()))
                store.db.execute("UPDATE owner_profile_v1 SET payload='{}'")
                with self.assertRaises(ValueError):
                    store.load(halted=False)
                store.clear(halted=False)
                self.assertIsNone(store.load(halted=False))

    def test_two_editors_preserve_newer_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owner.sqlite3"
            with ProfileStore(path) as first, ProfileStore(path) as second:
                initial = first.save(profile(), halted=False, expected_revision=None)
                with self.assertRaises(ProfileChangedError):
                    second.save(profile(hours_per_week=2), halted=False, expected_revision=None)
                updated = first.save(profile(hours_per_week=8), halted=False, expected_revision=initial)
                with self.assertRaises(ProfileChangedError):
                    second.clear(halted=False, expected_revision=initial)
                with self.assertRaises(ProfileChangedError):
                    second.save(profile(), halted=False, expected_revision=initial)
                self.assertEqual(second.load(halted=False)["hours_per_week"], 8)
                second.clear(halted=False, expected_revision=updated)
                self.assertIsNone(first.load(halted=False))

    def test_profile_strict_and_no_authority_fields(self):
        for changes in (dict(mode="other"),dict(budget="1"),dict(hours_per_week=True),
                        dict(hours_per_week=169),dict(sources=["unknown"]),
                        dict(naics=["5415"]),dict(cpv=["72*"]),dict(keywords=["secret@host"]),
                        dict(keywords=["software","software"]),dict(api_key="secret")):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                normalize_profile(profile(**changes))
        self.assertEqual(normalize_profile(profile(mode="catalyst",budget="100.5"))["budget"],"100.50")

    def test_halt_defaults(self):
        with ProfileStore(":memory:") as store:
            for state in (None,True,0):
                for action in (lambda:store.save(profile(),halted=state),
                               lambda:store.load(halted=state),lambda:store.clear(halted=state)):
                    with self.assertRaises(PermissionError):
                        action()

    def test_profile_revision_changes_and_normalization(self):
        self.assertEqual(profile_revision(profile()),profile_revision(profile(sources=list(reversed(profile()["sources"])))))
        self.assertNotEqual(profile_revision(profile()),profile_revision(profile(hours_per_week=21)))

    def test_codes_match_and_rank_all_before_limit(self):
        with LeadStore(":memory:") as store:
            for report in reports():
                store.record(report,now=NOW,halted=False)
            base=store.browse(now=NOW,halted=False)
            self.assertEqual(len(base["leads"]),4)
            result=store.browse(now=NOW,profile=profile(),limit=2,halted=False)
            self.assertEqual({r["source"] for r in result["leads"]},{"sam","ted"})
            self.assertTrue(all(r["profile_fit"]["reason"]=="DECLARED_CLASSIFICATION_MATCH" for r in result["leads"]))
            self.assertTrue(all(not r["profile_fit"]["execution_eligible"] and r["cash_exposure"] is None for r in result["leads"]))
            self.assertEqual(result["profile_revision"],profile_revision(profile()))
            self.assertEqual(len(result["leads"][0]["todo"]),9)
            self.assertNotIn("hours_per_week",json.dumps(result))

    def test_title_only_and_explicit_mismatch(self):
        with LeadStore(":memory:") as store:
            for report in reports():
                store.record(report,now=NOW,halted=False)
            result=store.browse(now=NOW,profile=profile(naics=["111111"]),halted=False)
            rows={r["source"]:r for r in result["leads"]}
            self.assertEqual(rows["sam"]["profile_fit"]["reason"],"CLASSIFICATION_MISMATCH")
            self.assertEqual(rows["canada"]["profile_fit"]["reason"],"TITLE_HINT_ONLY")
            self.assertGreater(rows["sam"]["profile_fit"]["priority"],rows["canada"]["profile_fit"]["priority"])

    def test_staleness_source_and_availability_precede_match(self):
        with LeadStore(":memory:") as store:
            for report in reports():
                store.record(report,now=NOW,halted=False)
            lead=store.browse(now=NOW,source="sam",halted=False)["leads"][0]
            self.assertEqual(assess_profile(profile(sources=[]),lead)["reason"],"SOURCE_NOT_SELECTED")
            self.assertEqual(assess_profile(profile(hours_per_week=0),lead)["reason"],"NO_DECLARED_AVAILABILITY")
            stale=store.browse(now=NOW+timedelta(days=2),profile=profile(),source="sam",halted=False)["leads"][0]
            self.assertEqual(stale["profile_fit"]["reason"],"REFRESH_OR_BLOCKED")

    def test_award_remains_intelligence_only(self):
        report=usaspending_search.search(spending.QUERY,
            transport=Mock(return_value=(200,spending.page([spending.award()]))),**OPTS)
        with LeadStore(":memory:") as store:
            store.record(report,now=NOW,halted=False)
            row=store.browse(now=NOW,profile=profile(),halted=False)["leads"][0]
            self.assertEqual(row["profile_fit"]["reason"],"CONTRACTOR_INTELLIGENCE_ONLY")
            self.assertFalse(row["execution_eligible"])

    def test_legacy_rows_without_classifications_remain_readable(self):
        report=copy.deepcopy(reports()[0])
        report["leads"][0].pop("metadata")
        with LeadStore(":memory:") as store:
            store.record(report,now=NOW,halted=False)
            row=store.browse(now=NOW,profile=profile(),halted=False)["leads"][0]
            self.assertNotIn("reported_codes",row)
            self.assertEqual(row["profile_fit"]["reason"],"TITLE_HINT_ONLY")

    def test_reported_code_validation_and_no_inference(self):
        self.assertEqual(reported_codes("usaspending",{"metadata":{"naicsCode":"541519"}}),[])
        with self.assertRaises(ValueError):
            reported_codes("canada",{"reported_codes":[{"scheme":"NAICS","code":"541519"}]})
        with self.assertRaises(ValueError):
            reported_codes("ted",{"reported_codes":[{"scheme":"CPV","code":"72*"}]})
