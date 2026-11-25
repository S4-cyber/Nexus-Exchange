import json
import unittest
from hashlib import sha256

from nexus_exchange.preview_security import security_report_refs

PINS = {"pyinstaller": "6.12.0", "packaging": "26.3"}
FLAGS = ("independently_verified", "vulnerabilities_cleared", "license_compliance_verified",
         "secrets_history_scanned", "frozen_binary_sbom_complete", "publisher_authenticated",
         "release_eligible", "external_authority")


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def seal(payload):
    payload = dict(payload)
    payload.pop("report_sha256", None)
    return canonical(dict(payload, report_sha256=sha256(canonical(payload)).hexdigest())) + b"\n"


def reports():
    build = dict(format="nexus-release-security-inventory-v1",
                 scope="INSTALLED_BUILD_ENVIRONMENT_NOT_FROZEN_CONTENTS",
                 python="3.12.10", sqlite="3.49.1", openssl="OpenSSL fixture",
                 unicode_database="15.0.0", pinned_packager_versions_checked=True,
                 distributions=[dict(name=k, version=v, license_expression_hint=None,
                                     license_metadata_hint=None) for k, v in sorted(PINS.items())],
                 **dict.fromkeys(FLAGS, False))
    source = dict(format="nexus-source-tripwires-v1", scope="APPLICATION_PYTHON_SOURCE_ONLY",
                  source_files=2, findings_count=0,
                  files=[dict(path=p, sha256="a" * 64, bytes=10, imports=[],
                              network_imports=[], findings=[])
                         for p in ("desktop.py", "nexus_exchange/fixture.py")],
                  **dict.fromkeys(FLAGS, False))
    return build, source


class PreviewSecurityTests(unittest.TestCase):
    def refs(self, build, source):
        return security_report_refs(seal(build), seal(source), packager_versions=PINS)

    def test_exact_report_bytes_are_bound(self):
        build, source = reports()
        raw = seal(build)
        refs = self.refs(build, source)
        self.assertEqual(refs["BUILD-INVENTORY.json"]["sha256"], sha256(raw).hexdigest())
        self.assertEqual(refs["SOURCE-REVIEW.json"]["bytes"], len(seal(source)))
        self.assertEqual(refs["BUILD-INVENTORY.json"]["report_sha256"], json.loads(raw)["report_sha256"])

    def test_resealed_nonzero_findings_and_false_authority_denied(self):
        build, source = reports()
        source["files"][0]["findings"] = [{"code": "FIXTURE", "line": 1}]
        with self.assertRaises(ValueError):
            self.refs(build, source)
        build, source = reports()
        source["findings_count"] = True
        with self.assertRaises(ValueError):
            self.refs(build, source)
        build, source = reports()
        build["release_eligible"] = True
        with self.assertRaises(ValueError):
            self.refs(build, source)

    def test_resealed_build_drift_and_extra_package_denied(self):
        build, source = reports()
        build["distributions"][0]["version"] = "0.0.1"
        with self.assertRaises(ValueError):
            self.refs(build, source)
        build, source = reports()
        build["distributions"].append(dict(name="unreviewed", version="1", license_expression_hint=None,
                                           license_metadata_hint=None))
        with self.assertRaises(ValueError):
            self.refs(build, source)

    def test_duplicate_paths_and_noncanonical_bytes_denied(self):
        build, source = reports()
        source["files"][1]["path"] = "desktop.py"
        with self.assertRaises(ValueError):
            self.refs(build, source)
        build, source = reports()
        for bad in (seal(build) + b"\n", b'{"x":1,"x":2}\n', b"x" * (256 * 1024 + 1)):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                security_report_refs(bad, seal(source), packager_versions=PINS)

    def test_wrong_internal_digest_denied(self):
        build, source = reports()
        value = json.loads(seal(build))
        value["report_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            security_report_refs(canonical(value) + b"\n", seal(source), packager_versions=PINS)


if __name__ == "__main__":
    unittest.main()
