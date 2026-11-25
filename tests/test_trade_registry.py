import unittest
from urllib.parse import urlsplit
from nexus_exchange.trade_registry import (SOURCES,KINDS,ACCESS,catalog,get_source,
    official_url,source_tasks,readiness)

class TradeRegistryTests(unittest.TestCase):
    def test_unique_and_bounded_registry(self):
        self.assertEqual(len(SOURCES),24)
        self.assertEqual(len({s.id for s in SOURCES}),len(SOURCES))
        self.assertTrue(all(s.kind in KINDS and s.access in ACCESS for s in SOURCES))

    def test_official_links_are_fixed_https(self):
        for source in SOURCES:
            for evidence in (False,True):
                url=official_url(source.id,evidence=evidence,halted=False)
                parsed=urlsplit(url)
                self.assertEqual(parsed.scheme,"https")
                self.assertTrue(parsed.hostname)
                self.assertIsNone(parsed.username)
                self.assertIsNone(parsed.password)
        for bad in ("https://evil.example","../sam","SAM",None):
            with self.assertRaises(ValueError):
                get_source(bad)

    def test_nonrevenue_sources_separated(self):
        self.assertEqual(get_source("grants").kind,"funding")
        self.assertEqual(get_source("usaspending").kind,"intelligence")
        self.assertEqual(get_source("challenges").kind,"prize")
        self.assertEqual(get_source("csl").kind,"compliance")
        self.assertNotIn("grants",{s.id for s in catalog(kind="earned",halted=False)})

    def test_filter_and_sort(self):
        rows=catalog(sector="International procurement",halted=False)
        self.assertEqual(len(rows),6)
        self.assertEqual(rows[-1].id,"ungm")
        self.assertEqual([s.id for s in catalog(query="cal eprocure",halted=False)],["california"])
        self.assertEqual(catalog(query="nonexistent",halted=False),())

    def test_source_status_not_execution_or_cash_verification(self):
        for source in SOURCES:
            status=readiness(source.id,halted=False)
            self.assertFalse(status["execution_eligible"])
            self.assertFalse(status["external_authority"])
            self.assertFalse(status["zero_capital_verified"])
            self.assertIsNone(status["cash_exposure"])
            self.assertEqual(len(source_tasks(source.id,halted=False)),4)
        self.assertIn("mock",readiness("sam",halted=False)["adapter_status"])
        self.assertIn("TED adapter",readiness("ted",halted=False)["adapter_status"])
        self.assertIn("FTS release adapter",readiness("uk_tender",halted=False)["adapter_status"])
        self.assertEqual(readiness("canada",halted=False)["adapter_status"],"catalog only")

    def test_fail_closed_halt_and_unknown_status(self):
        for state in (True,None,0):
            for call in (lambda:catalog(halted=state),
                lambda:official_url("sam",halted=state),
                lambda:source_tasks("sam",halted=state),
                lambda:readiness("sam",halted=state)):
                with self.assertRaises(PermissionError):
                    call()

    def test_invalid_filters(self):
        for kwargs in (dict(kind="unknown"),dict(sector="unknown"),dict(query="x"*121),
                       dict(query="a\nb"),dict(query=5)):
            with self.assertRaises(ValueError):
                catalog(halted=False,**kwargs)
        with self.assertRaises(ValueError):
            official_url("sam",evidence=1,halted=False)
