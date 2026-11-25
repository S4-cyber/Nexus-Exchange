import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nexus_exchange.activity_feed import ActivityFeed, with_shortlist
from nexus_exchange.engagement import cycle
from nexus_exchange.engagement_files import folder, INBOX, OUTPUTS, run_files
from nexus_exchange.event_store import EventStore
from test_lead_store import NOW, reports


class LiveActivityTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.store = EventStore(self.directory / "events.sqlite3")
        self.addCleanup(self.store.close)
        self.feed = ActivityFeed(self.store.db)

    def test_live_states_are_visible_from_separate_connection_before_cycle_returns(self):
        data = dict(zip(("sam", "ted", "uk_tender", "canada"), reports()))
        def search(source, *args):
            rows = self.feed.snapshot()
            if source == "uk_tender":
                self.assertIn(("Engaged", "UK Find a Tender"), [r[1:3] for r in rows])
                self.assertIn(("Pending", "CanadaBuys"), [r[1:3] for r in rows])
            else:
                self.assertIn(("Completed", "UK Find a Tender"), [r[1:3] for r in rows])
                self.assertTrue(any(r[1] == "Finding" and "https://" in r[3] for r in rows))
            return data[source]
        for _ in range(2):
            cycle(self.directory, lambda: False, lambda _: None, default_search=search, clock=lambda: NOW)
        rows = self.feed.snapshot()
        self.assertFalse(any(r[1] in ("Pending", "Engaged") for r in rows))
        self.assertEqual(sum(r[1] == "Finding" for r in rows), sum(data[k]["returned"] for k in ("uk_tender","canada")))

    def test_previous_brief_is_searchable_on_upgrade_without_duplicate_live_findings(self):
        previous = dict(finished=NOW.isoformat(), shortlist=[dict(source="canada", title="Earlier result",
                        url="https://example.org/notice", review="SOURCE_HELD", next_step="Check requirements.")])
        prior, = with_shortlist([], previous)
        self.assertEqual(prior[1:3], ("Finding", "Earlier result"))
        current = ("finding-unique", "Finding", "Earlier result", "CanadaBuys\nhttps://example.org/notice", NOW.isoformat())
        merged, = with_shortlist([current], previous)
        self.assertEqual(merged[0], "finding-unique")
        self.assertIn("Check requirements.", merged[3])
        self.assertIn("CanadaBuys", merged[3])

    def test_interrupt_and_reopen_clear_only_unfinished_rows(self):
        self.feed.put("one", [("a", "Completed", "Searched", ""), ("b", "Finding", "Notice", ""),
                              ("c", "Engaged", "Checking", ""), ("d", "Pending", "Later", "")], NOW)
        with_store = EventStore(self.directory / "events.sqlite3")
        try:
            reopened = ActivityFeed(with_store.db)
            reopened.settle()
        finally:
            with_store.close()
        self.assertEqual({r[0]: r[1] for r in self.feed.snapshot()},
                         dict(a="Completed", b="Finding", c="Stopped", d="Stopped"))
        self.feed.put("two", [("new", "Engaged", "Other cycle", "")], NOW)
        self.feed.settle("one")
        self.assertIn(("Engaged", "Other cycle"), [r[1:3] for r in self.feed.snapshot()])

    def test_json_conversion_preserves_order_duplicate_rows_and_strings(self):
        records = [{"sku":"0002","name":"A, B"}, {"name":'“Quoted”', "sku":"0001"}, {"sku":"0002","name":"A, B"}]
        inbox = folder(self.directory, INBOX)
        (inbox / "stock.JSON").write_text(json.dumps(records), encoding="utf-8-sig")
        steps = []
        result = run_files(self.directory, lambda: False, report=lambda rows: steps.extend(r[1] for r in rows))
        self.assertEqual(steps, ["Pending", "Engaged", "Completed"])
        item, = result["items"]
        dest = folder(self.directory, OUTPUTS) / item["output"]
        with dest.open(encoding="utf-8", newline="") as handle:
            self.assertEqual(list(csv.reader(handle)), [["sku","name"], ["0002","A, B"], ["0001",'“Quoted”'], ["0002","A, B"]])
        self.assertEqual(run_files(self.directory, lambda: False)["existing"], 1)
        dest.write_text("edited", encoding="utf-8")
        held, = run_files(self.directory, lambda: False)["items"]
        self.assertIn("existing output differs", held["reason"])
        self.assertEqual(dest.read_text(), "edited")

    def test_invalid_records_have_specific_reasons_without_exposing_values(self):
        cases = [(b'[{"a":"hidden","a":"secret"}]', "unique name"),
                 (b'[{"a":6}]', "text values"), (b'[{"a":"hidden"},{"b":"hidden"}]', "same set"),
                 (b'[{"a":"=hidden"}]', "formula-like"), (b'[]', "1\u20132,000"),
                 (b'{bad', "UTF-8 JSON")]
        path = folder(self.directory, INBOX) / "input.json"
        for raw, message in cases:
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                item, = run_files(self.directory, lambda: False)["items"]
                self.assertEqual(item["status"], "held")
                self.assertIn(message, item["reason"])
                self.assertNotIn("hidden", repr(item))
        self.assertEqual(list(folder(self.directory, OUTPUTS).iterdir()), [])

    def test_file_workspace_issue_keeps_source_results_visible(self):
        (self.directory / OUTPUTS).write_text("occupied")
        data = dict(zip(("sam","ted","uk_tender","canada"), reports()))
        brief = cycle(self.directory, lambda: False, lambda _: None, clock=lambda: NOW,
                      default_search=lambda source,*args: data[source])
        self.assertIn("work folders", brief["jobs"]["issue"])
        self.assertTrue(brief["shortlist"])
        self.assertIn(("Needs attention","Process local work files"), [r[1:3] for r in self.feed.snapshot()])
