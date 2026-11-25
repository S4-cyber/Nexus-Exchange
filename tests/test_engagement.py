import base64
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from nexus_exchange import account_providers as api
from nexus_exchange.account_vault import AccountVault
from nexus_exchange.engagement import BRIEF, cycle
from nexus_exchange.engagement_files import folder, INBOX, OUTPUTS, run_files
from nexus_exchange.owner_profile import ProfileStore
from test_lead_store import NOW, reports

def active():
    return False


class EngageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    @staticmethod
    def search(source, *args):
        if source == "canada":
            raise OSError("source timeout with untrusted text")
        return dict(format="nexus-fts-research-v1", returned=0, leads=[], truncated=False, page_sha256=["a"*64])

    def test_first_run_partial_coverage_produces_checked_files_offline(self):
        raw = b"id,value\n1,abc\n2,\n"
        (folder(self.dir, INBOX) / "job.csv").write_bytes(raw)
        brief = cycle(self.dir, active, lambda _: None, default_search=self.search)
        self.assertEqual(brief["status"], "Partial coverage")
        self.assertEqual([r["status"] for r in brief["sources"]], ["Searched", "Unavailable"])
        self.assertEqual(brief["jobs"]["produced"], 1)
        self.assertNotIn("untrusted", (self.dir / BRIEF).read_text())
        self.assertFalse((self.dir / "owner-profile.sqlite3").exists())
        dest, = folder(self.dir, OUTPUTS).glob("*.csv")
        self.assertIn(b'"value","2","1","0","1","1","0","3"', dest.read_bytes())
        self.assertEqual(run_files(self.dir, active)["existing"], 1)
        dest.write_bytes(b"manually edited")
        self.assertEqual(run_files(self.dir, active)["held"], 1)
        self.assertEqual(dest.read_bytes(), b"manually edited")

    def test_real_adapter_shapes_archive_and_rank_repeatably(self):
        by_source = {source: report for source, report in zip(("sam","ted","uk_tender","canada"), reports())}
        def search(source, *args):
            return by_source[source]
        one = cycle(self.dir, active, lambda _: None, default_search=search, clock=lambda: NOW)
        two = cycle(self.dir, active, lambda _: None, default_search=search, clock=lambda: NOW)
        self.assertTrue(one["shortlist"])
        self.assertEqual(one["shortlist"], two["shortlist"])
        self.assertTrue(all(row["next_step"] and row["url"].startswith("https://") for row in one["shortlist"]))
        self.assertEqual(sum(row["saved"] for row in two["sources"]), 0)

    def test_cancel_keeps_prior_brief_and_blocks_next_source(self):
        (self.dir / BRIEF).write_text("prior")
        seen = []
        def interrupt(source, *args):
            seen.append(source)
            return self.search(source, *args)
        with self.assertRaises(PermissionError):
            cycle(self.dir, lambda: bool(seen), lambda _: None, default_search=interrupt)
        self.assertEqual(seen, ["uk_tender"])
        self.assertEqual((self.dir / BRIEF).read_text(), "prior")

    def test_advanced_profile_overrides_default_sources_and_blank_key(self):
        with ProfileStore(self.dir / "owner-profile.sqlite3") as profiles:
            profiles.save(dict(mode="genesis", budget="0", hours_per_week=3, sources=["sam"],
                               naics=[], cpv=[], keywords=[]), halted=False)
        with patch("nexus_exchange.engagement.execute_discovery") as run:
            brief = cycle(self.dir, active, lambda _: None)
            run.assert_not_called()
        self.assertEqual(brief["status"], "No sources enabled")
        self.assertIn("SAM.gov", brief["notes"][0])

    def test_unsafe_input_is_held(self):
        (folder(self.dir, INBOX) / "bad.csv").write_text("a\n=formula\n")
        self.assertEqual(run_files(self.dir, active)["held"], 1)
        self.assertEqual(list(folder(self.dir, OUTPUTS).iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_native_protection_roundtrip_tamper_and_forget(self):
        vault = AccountVault(self.dir)
        vault.save("sam", {"key": "fixture-plaintext-value"})
        raw = vault.path("sam").read_bytes()
        self.assertNotIn(b"fixture-plaintext-value", raw)
        self.assertEqual(vault.load("sam"), {"key": "fixture-plaintext-value"})
        vault.path("sam").write_bytes(raw[:-8])
        with self.assertRaises(OSError):
            vault.load("sam")
        vault.forget("sam")
        self.assertIsNone(vault.load("sam"))


class ProviderTests(unittest.TestCase):
    def test_claim_then_read_balances_only(self):
        setup = base64.b64encode(b"https://bridge.simplefin.org/simplefin/claim/fixture").decode()
        access = "https://user:pass@bridge.simplefin.org/simplefin"
        stamp = int(time.time())
        data = dict(errlist=[], accounts=[dict(currency="USD", **{"available-balance":"19.02","balance-date":stamp})])
        with patch.object(api, "request", side_effect=[access.encode(), json.dumps(data).encode()]) as request:
            self.assertEqual(api.claim_bank(setup)["access"], access)
            bank = api.balances(access)
        self.assertEqual(request.call_args.args[2], "/simplefin/accounts?version=2&balances-only=1")
        self.assertEqual(str(api.planning_limit({"budget":"91.00"}, bank, stamp)), "19.02")
        self.assertEqual(str(api.planning_limit({"budget":"3.00"}, bank, stamp)), "3.00")
        self.assertEqual(api.planning_limit({"budget":"12"}, bank, stamp+86401), 0)

    def test_untrusted_claim_blocked_before_network_and_multiple_accounts_zero(self):
        with patch.object(api, "request") as request:
            with self.assertRaises(ValueError):
                api.claim_bank(base64.b64encode(b"https://untrusted.example/simplefin/claim/abc").decode())
            request.assert_not_called()
            request.return_value = b'{"errlist":[],"accounts":[{"currency":"USD"},{"currency":"USD"}]}'
            self.assertIsNone(api.balances("https://a:b@bridge.simplefin.org/simplefin")["available"])

    def test_pkce_distinct_state_and_provider_identity(self):
        client = "00000000-1111-2222-3333-444444444444"
        url, state, verifier = api.consent(client)
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["state"], [state])
        self.assertNotEqual(api.consent(client)[1], state)
        self.assertNotIn(verifier, url)
        self.assertEqual(params["redirect_uri"], [api.REDIRECT])
        with patch.object(api, "request", side_effect=[b'{"access_token":"demo","token_type":"Bearer","expires_in":1200,"refresh_token":"renew"}',
                                                        b'{"sub":"uid","accounts":[{}]}']) as req:
            grant = api.authorize_document(client, verifier, "code")
        self.assertEqual(grant["refresh"], "renew")
        self.assertEqual(req.call_args.args, (api.DOC, "GET", "/oauth/userinfo"))
