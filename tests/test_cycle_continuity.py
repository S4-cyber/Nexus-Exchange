import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from nexus_exchange import engagement, lead_store
from nexus_exchange.activity_feed import ActivityFeed
from nexus_exchange.cycle_history import latest
from nexus_exchange.engagement_files import folder, INBOX, OUTPUTS
from nexus_exchange.event_store import EventStore
from test_lead_store import NOW, reports


class CycleContinuityTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.dbfile = self.directory / "scout-leads.sqlite3"
        self.source_data = dict(zip(("sam", "ted", "uk_tender", "canada"), reports()))
        self.calls = []
        (folder(self.directory, INBOX) / "job.json").write_text('[{"name":"fixture"}]')

    def search(self, source, *args):
        self.calls.append(source)
        return self.source_data[source]

    def run_cycle(self, stopped=lambda: False):
        return engagement.cycle(self.directory, stopped, lambda _: None,
                                default_search=self.search, clock=lambda: NOW)

    def activity(self):
        events = EventStore(self.directory / "events.sqlite3")
        try:
            return ActivityFeed(events.db).snapshot()
        finally:
            events.close()

    def test_full_archive_keeps_prior_evidence_and_finishes_independent_files(self):
        with lead_store.LeadStore(self.dbfile) as store:
            store.record(self.source_data["sam"], now=NOW, halted=False)
        with patch.object(lead_store, "MAX_ROWS", 1):
            brief = self.run_cycle()
        self.assertEqual(self.calls, ["uk_tender"])
        self.assertEqual([s["status"] for s in brief["sources"]], ["Not saved", "Skipped"])
        self.assertEqual(brief["status"], "Research needs attention")
        self.assertEqual([r["source"] for r in brief["shortlist"]], ["sam"])
        self.assertEqual(brief["jobs"]["produced"], 1)
        self.assertEqual(latest(self.directory), brief)
        self.assertFalse(any(r[1] == "Finding" for r in self.activity()))
        self.assertIn(("Skipped", "CanadaBuys"), [r[1:3] for r in self.activity()])
        with lead_store.LeadStore(self.dbfile) as store:
            self.assertEqual(store.browse(now=NOW, halted=False)["matched"], 1)

    def test_unreadable_archive_does_not_hide_file_results_or_fabricate_a_shortlist(self):
        raw = b"not a local opportunity database" * 8
        self.dbfile.write_bytes(raw)
        brief = self.run_cycle()
        self.assertEqual(brief["shortlist"], [])
        self.assertEqual(brief["jobs"]["produced"], 1)
        self.assertEqual(self.dbfile.read_bytes(), raw)
        self.assertEqual(self.calls, ["uk_tender"])
        self.assertIn(("Needs attention", "Compile review shortlist"), [r[1:3] for r in self.activity()])
        self.assertIn("shortlist", " ".join(brief["notes"]).lower())
        self.assertNotIn(raw.decode()[:15], json.dumps(brief))

    def test_wrong_source_is_rejected_and_next_source_can_succeed(self):
        self.source_data["uk_tender"] = self.source_data["sam"]
        brief = self.run_cycle()
        self.assertEqual(brief["status"], "Partial coverage")
        self.assertEqual([(s["status"], s["saved"]) for s in brief["sources"]],
                         [("Not saved", 0), ("Searched", 1)])
        self.assertEqual([r["source"] for r in brief["shortlist"]], ["canada"])
        self.assertEqual(brief["jobs"]["produced"], 1)

    def test_unusable_optional_instructions_do_not_interrupt_verified_findings(self):
        self.source_data["uk_tender"]["leads"][0]["todo"] = ["invalid optional metadata"]
        brief = self.run_cycle()
        self.assertEqual(brief["status"], "Completed")
        self.assertEqual(brief["jobs"]["produced"], 1)
        findings = [r for r in self.activity() if r[1] == "Finding"]
        self.assertEqual(len(findings), 2)
        self.assertNotIn("invalid optional metadata", repr(findings))

    def test_unencodable_title_is_rejected_and_optional_instruction_is_display_safe(self):
        self.source_data["uk_tender"]["leads"][0]["title"] = "bad " + chr(0xD800)
        self.source_data["canada"]["leads"][0]["todo"] = [{"instruction": "Review " + chr(0xD800)}]
        brief = self.run_cycle()
        self.assertEqual([s["status"] for s in brief["sources"]], ["Not saved", "Searched"])
        self.assertEqual(brief["jobs"]["produced"], 1)
        self.assertEqual([r["source"] for r in brief["shortlist"]], ["canada"])
        findings = [r for r in self.activity() if r[1] == "Finding"]
        self.assertEqual(len(findings), 1)
        self.assertNotIn(chr(0xD800), findings[0][3])

    def test_read_failure_after_successful_search_does_not_claim_full_success(self):
        with patch.object(engagement, "compile_brief", side_effect=ValueError("private fixture")):
            brief = self.run_cycle()
        self.assertEqual(brief["status"], "Research needs attention")
        self.assertEqual([s["status"] for s in brief["sources"]], ["Searched", "Searched"])
        self.assertEqual(brief["jobs"]["produced"], 1)
        self.assertNotIn("private fixture", json.dumps(brief))
        self.assertFalse(brief["shortlist_available"])
        self.assertEqual(engagement.shortlist_summary(brief), "Shortlist unavailable")
        self.assertIn("Shortlist unavailable", engagement.brief_text(brief))
        self.assertEqual(engagement.shortlist_summary({"shortlist": []}), "Shortlisted 0")

    def test_next_cycle_recovers_and_does_not_duplicate_completed_files(self):
        with patch.object(lead_store.LeadStore, "record", side_effect=OSError("fixture")):
            first = self.run_cycle()
        second = self.run_cycle()
        self.assertEqual(first["status"], "Research needs attention")
        self.assertEqual(second["status"], "Completed")
        self.assertEqual(second["jobs"]["existing"], 1)
        self.assertEqual(second["jobs"]["produced"], 0)
        self.assertEqual(len(second["shortlist"]), 2)
        self.assertEqual(self.calls, ["uk_tender", "uk_tender", "canada"])

    def test_halt_during_storage_failure_preserves_previous_brief_and_prevents_file_work(self):
        triggered = False
        def fail(*args, **kwargs):
            nonlocal triggered
            triggered = True
            raise ValueError("archive rejected the batch")
        prior = self.directory / engagement.BRIEF
        prior.write_text("prior")
        with patch.object(lead_store.LeadStore, "record", new=fail), self.assertRaises(PermissionError):
            self.run_cycle(lambda: triggered)
        self.assertEqual(self.calls, ["uk_tender"])
        self.assertEqual(prior.read_text(), "prior")
        self.assertEqual(list(folder(self.directory, OUTPUTS).iterdir()), [])
