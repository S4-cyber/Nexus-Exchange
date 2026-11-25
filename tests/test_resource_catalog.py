import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nexus_exchange.resource_catalog import parse_catalog, shortlist, read_catalog, MAX_BYTES


def fixture():
    row = dict(repository="example/review-tool", revision="a" * 40,
               category="security", priority=1, workstreams=["H06", "H07"],
               license_hint="MIT", license_basis="METADATA_ONLY",
               evidence=[dict(path="README.md", blob="b" * 40)],
               purpose="Review owned code.", next_check="Audit the pinned dependencies.",
               adoption="REFERENCE_ONLY")
    return dict(format="nexus-awesome-catalog-v1", surveyed_at="2026-11-25",
                topic="https://github.com/topics/awesome", auto_install=False,
                auto_execute=False, external_authority=False, resources=[row])


def encoded(value):
    return json.dumps(value).encode("ascii")


class CatalogTests(unittest.TestCase):
    def test_reference_only_shortlist_is_pinned_and_deterministic(self):
        data = fixture()
        data["resources"].append(dict(data["resources"][0], repository="example/second", priority=2))
        catalog = parse_catalog(encoded(data))
        rows = shortlist(catalog, workstream="H06", category="security")
        self.assertEqual([row["repository"] for row in rows], ["example/review-tool", "example/second"])
        self.assertEqual(rows[0]["url"], "https://github.com/example/review-tool/tree/" + "a" * 40)
        self.assertEqual(shortlist(catalog, workstream="H08"), [])
        self.assertFalse(catalog["auto_execute"])
        self.assertEqual(rows[0]["adoption"], "REFERENCE_ONLY")
        rows[0]["purpose"] = "Changed by consumer."
        self.assertEqual(shortlist(catalog)[0]["purpose"], "Review owned code.")

    def test_authority_and_unknown_fields_are_rejected(self):
        for key, value in (("auto_install", True), ("auto_execute", 0), ("external_authority", None), ("command", "run")):
            data = fixture()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_catalog(encoded(data))
        for key, value in (("adoption", "APPROVED"), ("shell", "run"), ("priority", True)):
            data = fixture()
            data["resources"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_catalog(encoded(data))

    def test_unpinned_or_untrusted_resource_identity_rejected(self):
        for key, value in (("repository", "example/tool?x=1"), ("repository", "https://elsewhere/tool"),
                           ("revision", "main"), ("workstreams", ["H09"]), ("category", "unknown"),
                           ("evidence", [dict(path="../README.md", blob="a" * 40)])):
            data = fixture()
            data["resources"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_catalog(encoded(data))

    def test_duplicate_repository_and_malformed_json_rejected(self):
        data = fixture()
        row = copy.deepcopy(data["resources"][0])
        row["repository"] = "Example/Review-Tool"
        data["resources"].append(row)
        for raw in (encoded(data), b'{"a":1,"a":2}', b'{"x":NaN}', b"x" * (MAX_BYTES + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                parse_catalog(raw)

    def test_bounded_local_read_and_invalid_filter(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_bytes(encoded(fixture()))
            catalog = read_catalog(path)
            with self.assertRaises(ValueError):
                shortlist(catalog, workstream="H00")
            with self.assertRaises(ValueError):
                shortlist(catalog, category="all")
            path.write_bytes(b"x" * (MAX_BYTES + 1))
            with self.assertRaises(ValueError):
                read_catalog(path)


class RepositoryCatalogTests(unittest.TestCase):
    def test_curated_repository_inventory(self):
        path = Path(__file__).resolve().parents[1] / "resources" / "awesome" / "catalog.json"
        catalog = read_catalog(path)
        rows = shortlist(catalog)
        self.assertGreaterEqual(len(rows), 16)
        self.assertIn("sindresorhus/awesome", {row["repository"] for row in rows})
        for workstream in ("H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08"):
            self.assertTrue(shortlist(catalog, workstream=workstream))
        for category in ("local-inference", "agents", "security", "data"):
            self.assertTrue(shortlist(catalog, category=category))
        self.assertTrue(all(row["adoption"] == "REFERENCE_ONLY" for row in rows))


if __name__ == "__main__":
    unittest.main()
