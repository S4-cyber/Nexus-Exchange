import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from nexus_exchange.release_security import scan_source,scan_tree,inventory,PACKAGER,_source


class SecurityInventoryTests(unittest.TestCase):
    def codes(self,source,path="nexus_exchange/example.py"):
        return {row["code"] for row in scan_source(path,source.encode("utf-8"))["findings"]}

    def test_repository_source_tripwires(self):
        result=scan_tree(Path(__file__).resolve().parents[1])
        findings=[(row["path"],f["code"],f["line"]) for row in result["files"] for f in row["findings"]]
        self.assertEqual(findings,[])
        self.assertGreaterEqual(result["source_files"],68)
        self.assertFalse(result["vulnerabilities_cleared"])

    def test_local_imports_and_reviewed_network_origin(self):
        source="from .scout import normalize\nfrom urllib.parse import urlencode\nimport csv\n"
        self.assertEqual(self.codes(source),set())
        self.assertEqual(self.codes("import http.client\nhttp.client.HTTPSConnection(HOST,443)\n",
                                    "nexus_exchange/sam_search.py"),set())
        self.assertIn("HTTPS_ORIGIN_REVIEW_REQUIRED",
            self.codes("import http.client\nhttp.client.HTTPSConnection(user_url)\n",
                       "nexus_exchange/sam_search.py"))
        self.assertIn("NETWORK_IMPORT_OUTSIDE_REVIEWED_SURFACE",
            self.codes("from urllib import request\n"))
        self.assertIn("NETWORK_IMPORT_OUTSIDE_REVIEWED_SURFACE",self.codes("import socket\n"))

    def test_restricted_dynamic_calls_and_import_aliases(self):
        source="import subprocess as p\nfrom builtins import eval as e\nimport os as system\np.run('x',shell=True)\ne('x')\nsystem.system('x')\n"
        self.assertTrue({"RESTRICTED_IMPORT","RESTRICTED_DYNAMIC_OR_PROCESS_CALL","SHELL_TRUE"}<=self.codes(source))
        self.assertIn("RESTRICTED_SQLITE_CALL",self.codes("db.enable_load_extension(True)\n"))
        self.assertIn("NON_STDLIB_APPLICATION_IMPORT",self.codes("import unexpected_dependency\n"))
        self.assertIn("INSECURE_TRANSPORT_CALL",self.codes("import ssl\nssl._create_unverified_context()\n"))

    def test_secret_shape_does_not_echo_secret(self):
        fake="ghp_"+"A"*36
        report=scan_source("nexus_exchange/example.py",("TOKEN="+repr(fake)).encode())
        self.assertEqual(report["findings"],[dict(code="GITHUB_TOKEN_SHAPE",line=1)])
        self.assertNotIn(fake,repr(report))

    def test_malformed_and_extra_subpackages_rejected(self):
        with self.assertRaises(ValueError):
            scan_source("nexus_exchange/example.py",b"def (")
        with self.assertRaises(ValueError):
            scan_source("../outside.py",b"x=1")
        with TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"nexus_exchange").mkdir()
            (root/"nexus_exchange"/"new_package").mkdir()
            (root/"desktop.py").write_text("pass")
            with self.assertRaises(ValueError):
                scan_tree(root)

    def test_wildcard_import_requires_explicit_review(self):
        for source in ("from os import *\n", "from builtins import *\n",
                       "from .scout import *\n", "from http.client import *\n"):
            with self.subTest(source=source):
                self.assertIn("WILDCARD_IMPORT_REVIEW_REQUIRED",self.codes(source))

    def test_same_size_source_replacement_rejected(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/"source.py"
            path.write_bytes(b"x=1\n")
            replacement=Path(temp)/"replacement.py"
            replacement.write_bytes(b"x=2\n")
            original_lstat=Path.lstat
            swapped=False

            def swap_after_stat(target,*args,**kwargs):
                nonlocal swapped
                info=original_lstat(target,*args,**kwargs)
                if target==path and not swapped:
                    swapped=True
                    replacement.replace(path)
                return info

            with patch.object(Path,"lstat",swap_after_stat):
                with self.assertRaises(ValueError):
                    _source(path)
            self.assertTrue(swapped)
            self.assertEqual(_source(path),b"x=2\n")

    def distributions(self,**changes):
        values=dict(PACKAGER,pip="25.1")
        values.update(changes)
        return [SimpleNamespace(metadata={"Name":k,"License-Expression":"MIT"},version=v)
                for k,v in values.items()]

    def test_exact_build_inventory_and_no_security_clearance(self):
        result=inventory(self.distributions(),expect_packager=True)
        self.assertTrue(result["pinned_packager_versions_checked"])
        self.assertEqual(len(result["distributions"]),len(PACKAGER)+1)
        for k in ("independently_verified","license_compliance_verified","vulnerabilities_cleared",
                  "frozen_binary_sbom_complete","release_eligible"):
            self.assertIs(result[k],False)

    def test_version_drift_unexpected_package_duplicate_and_invalid_metadata(self):
        for changes in ({"pyinstaller":"6.13.0"},{"unexpected-package":"1.0"}):
            with self.assertRaises(ValueError):
                inventory(self.distributions(**changes),expect_packager=True)
        rows=self.distributions()
        with self.assertRaises(ValueError):
            inventory(rows+[rows[0]],expect_packager=True)
        with self.assertRaises(ValueError):
            inventory([SimpleNamespace(metadata={"Name":"../private"},version="1")])

    def test_long_license_metadata_unresolved_and_stable_report(self):
        dist=SimpleNamespace(metadata={"Name":"Owned_Fixture","License":"x"*1000},version="1.0")
        result=inventory([dist])
        self.assertIsNone(result["distributions"][0]["license_metadata_hint"])
        self.assertEqual(result,inventory([dist]))


if __name__=="__main__":
    unittest.main()
