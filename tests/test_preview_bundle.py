import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256

from nexus_exchange.preview_bundle import (
    write_bundle,verify_bundle,EXE,CHECKSUM,GENESIS,MANIFEST,
    _canonical,_json,_DIAGNOSTIC_FLAGS,_REQUIRED_CHECKS,_DIAGNOSTIC_IDS,
)


def report(**changes):
    # This fixture tests metadata validation; the real diagnostic has its
    # own integration suite and runs in CI during bundle creation.
    result=dict(format="nexus-owned-genesis-diagnostic-v1",mode="OWNED_OFFLINE_FIXTURE_ONLY",
        checks=list(_REQUIRED_CHECKS),external_requests=0,fixture_transport_calls=1,
        restored_database_count=12,correspondence_event_count=1,
        **{key:sha256(key.encode("ascii")).hexdigest() for key in _DIAGNOSTIC_IDS},
        council_attempts=2,assumption_references=17,independently_verified_assumptions=0,
        modeled_pre_payment_exposure_cents=0,modeled_probability_adjusted_net_cents=12000,
        hypothetical_gross_cents=20000,hypothetical_received_cents=20000,
        hypothetical_outstanding_cents=0,hypothetical_protected_reserve_cents=5000,
        hypothetical_reinvestment_cents=15000,**dict.fromkeys(_DIAGNOSTIC_FLAGS,False))
    result.update(changes)
    return dict(result,report_sha256=sha256(_json(result).encode("ascii")).hexdigest())


class PreviewBundleTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)
        self.exe=b"MZ"+b"owned synthetic executable bytes; not a real PE"
        (self.path/EXE).write_bytes(self.exe)
        self.identity=dict(commit="a"*40,tree="b"*40,run_id=123,attempt=1,event="pull_request")

    def write(self,diagnostic=None,**changes):
        opts=dict(self.identity)
        opts.update(changes)
        return write_bundle(self.path,diagnostic=report() if diagnostic is None else diagnostic,**opts)

    def test_consistent_bundle_and_explicit_external_build_pins(self):
        value=self.write()
        self.assertEqual(value,verify_bundle(self.path,expected_commit="a"*40,
                                           expected_tree="b"*40,expected_run=123))
        self.assertEqual(value["executable"]["sha256"],sha256(self.exe).hexdigest())
        self.assertEqual((self.path/CHECKSUM).read_bytes(),(sha256(self.exe).hexdigest()+"\n").encode())
        for flag in ("signed","publisher_authenticated","production_ready","release_eligible",
                     "external_authority","actual_revenue_verified"):
            self.assertIs(value[flag],False)
        for pins in (dict(expected_commit="c"*40),dict(expected_tree="d"*40),dict(expected_run=124)):
            with self.assertRaises(ValueError):
                verify_bundle(self.path,**pins)

    def test_executable_tamper_even_with_rewritten_checksum(self):
        self.write()
        altered=self.exe+b"changed"
        (self.path/EXE).write_bytes(altered)
        (self.path/CHECKSUM).write_text(sha256(altered).hexdigest()+"\n",encoding="ascii",newline="")
        with self.assertRaises(ValueError):
            verify_bundle(self.path)

    def test_scoped_diagnostic_evidence_is_required(self):
        for diagnostic in (report(scout_review_scope_sha256="invalid"),
                           report(checks=[x for x in _REQUIRED_CHECKS if x!="SCOPED_PROVENANCE_RECOVERED"])):
            with self.subTest(diagnostic=diagnostic),self.assertRaises(ValueError):
                self.write(diagnostic=diagnostic)
        self.assertFalse((self.path/MANIFEST).exists())

    def test_exact_sequence_includes_correspondence_and_recovery(self):
        checks=list(_REQUIRED_CHECKS)
        for altered in (checks[1:],checks[::-1],checks+["UNEXPECTED"],
                        [x for x in checks if x!="DURABLE_CORRESPONDENCE_HISTORY"]):
            with self.subTest(altered=altered),self.assertRaises(ValueError):
                self.write(report(checks=altered))
        self.assertFalse((self.path/MANIFEST).exists())

    def test_all_provenance_ids_and_restored_history_required(self):
        for key in _DIAGNOSTIC_IDS:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.write(report(**{key:"missing"}))
        for changes in (dict(correspondence_event_count=True),dict(correspondence_event_count=0),
                        dict(restored_database_count=0),dict(restored_database_count=True),
                        dict(restored_database_count=65),
                        dict(correspondence_head_sha256=report()["correspondence_thread_id"])):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.write(report(**changes))
        self.assertFalse((self.path/MANIFEST).exists())

    def test_external_attempt_and_event_pins(self):
        expected=self.write()
        self.assertEqual(expected,verify_bundle(self.path,expected_attempt=1,
                                               expected_event="pull_request"))
        for pins in (dict(expected_attempt=2),dict(expected_attempt=True),
                     dict(expected_event="push"),dict(expected_event="unknown")):
            with self.subTest(pins=pins),self.assertRaises(ValueError):
                verify_bundle(self.path,**pins)

    def test_diagnostic_and_manifest_tampering(self):
        self.write()
        original=(self.path/GENESIS).read_bytes()
        (self.path/GENESIS).write_bytes(_canonical(report(payment_received=True)))
        with self.assertRaises(ValueError):
            verify_bundle(self.path)
        (self.path/GENESIS).write_bytes(original)
        manifest=json.loads((self.path/MANIFEST).read_bytes())
        manifest["signed"]=True
        (self.path/MANIFEST).write_bytes(_canonical(manifest))
        with self.assertRaises(ValueError):
            verify_bundle(self.path)

    def test_invalid_diagnostic_precedes_metadata_writes(self):
        for data in (report(external_requests=1),report(checks=[]),report(funds_available=True),
                     report(hypothetical_reinvestment_cents=15001),dict(report(),report_sha256="0"*64)):
            with self.assertRaises(ValueError):
                self.write(data)
        for name in (CHECKSUM,GENESIS,MANIFEST):
            self.assertFalse((self.path/name).exists())

    def test_no_overwrite_and_invalid_build_metadata(self):
        for changes in (dict(commit="main"),dict(run_id=True),dict(event="unknown"),dict(attempt=0)):
            with self.assertRaises(ValueError):
                self.write(**changes)
        result=self.write()
        with self.assertRaises(ValueError):
            self.write()
        self.assertEqual(result,verify_bundle(self.path))

    def test_missing_and_noncanonical_metadata(self):
        self.write()
        manifest=(self.path/MANIFEST).read_bytes()
        for raw in (b'{"x":1,"x":2}\n',manifest+b"\n",b"x"*65537):
            (self.path/MANIFEST).write_bytes(raw)
            with self.assertRaises(ValueError):
                verify_bundle(self.path)
        (self.path/MANIFEST).write_bytes(manifest)
        (self.path/CHECKSUM).unlink()
        with self.assertRaises(ValueError):
            verify_bundle(self.path)

    def test_executable_header_check_and_symlink(self):
        (self.path/EXE).write_bytes(b"not windows")
        with self.assertRaises(ValueError):
            self.write()
        target=self.path/"other.bin"
        target.write_bytes(self.exe)
        (self.path/EXE).unlink()
        try:
            (self.path/EXE).symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable on runner")
        with self.assertRaises(ValueError):
            self.write()


    def security_files(self):
        from test_preview_security import reports, seal
        from nexus_exchange.release_security import PACKAGER
        from nexus_exchange.preview_security import BUILD_REPORT, SOURCE_REPORT
        build,source=reports()
        build["distributions"]=[dict(name=k,version=v,license_expression_hint=None,
                                      license_metadata_hint=None) for k,v in sorted(PACKAGER.items())]
        (self.path/BUILD_REPORT).write_bytes(seal(build))
        (self.path/SOURCE_REPORT).write_bytes(seal(source))
        return build,source

    def test_security_bound_bundle_and_required_policy(self):
        from nexus_exchange.preview_security import BUILD_REPORT, SOURCE_REPORT
        self.security_files()
        value=self.write(require_security_reports=True)
        self.assertEqual(value["format"],"nexus-windows-preview-bundle-v2")
        for name in (BUILD_REPORT,SOURCE_REPORT):
            raw=(self.path/name).read_bytes()
            self.assertEqual(value["security_reports"][name]["sha256"],sha256(raw).hexdigest())
        self.assertEqual(value,verify_bundle(self.path,require_security_reports=True))
        self.assertFalse(value["publisher_authenticated"])

    def test_security_report_resealed_tamper_and_missing_file_denied(self):
        from nexus_exchange.preview_security import SOURCE_REPORT
        from test_preview_security import seal
        _,source=self.security_files()
        self.write(require_security_reports=True)
        source["files"][0]["sha256"]="b"*64
        (self.path/SOURCE_REPORT).write_bytes(seal(source))
        with self.assertRaises(ValueError):
            verify_bundle(self.path)
        (self.path/SOURCE_REPORT).unlink()
        with self.assertRaises(ValueError):
            verify_bundle(self.path)

    def test_security_required_writer_rejects_missing_pair_before_writes(self):
        from nexus_exchange.preview_security import SOURCE_REPORT
        with self.assertRaises(ValueError):
            self.write(require_security_reports=True)
        self.security_files()
        (self.path/SOURCE_REPORT).unlink()
        with self.assertRaises(ValueError):
            self.write()
        self.assertFalse((self.path/MANIFEST).exists())
        self.assertFalse((self.path/GENESIS).exists())

    def test_legacy_verification_explicitly_cannot_meet_security_policy(self):
        old=self.write()
        self.assertEqual(old,verify_bundle(self.path))
        self.security_files()
        self.assertEqual(old,verify_bundle(self.path))
        with self.assertRaises(ValueError):
            verify_bundle(self.path,require_security_reports=True)


if __name__=="__main__":
    unittest.main()
