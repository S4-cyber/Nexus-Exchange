import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nexus_exchange.genesis_diagnostic import run_diagnostic, FORMAT
from nexus_exchange.lead_store import _digest,_json


class GenesisDiagnosticTests(unittest.TestCase):
    def test_complete_isolated_lifecycle_and_determinism(self):
        with patch("nexus_exchange.sam_search._request",side_effect=AssertionError("network not permitted")) as real_transport:
            first=run_diagnostic(confirmed=True)
            second=run_diagnostic(confirmed=True)
            real_transport.assert_not_called()
        self.assertEqual(first,second)
        self.assertEqual(first["format"],FORMAT)
        self.assertEqual(first["fixture_transport_calls"],1)
        self.assertEqual(first["external_requests"],0)
        self.assertEqual(first["council_attempts"],2)
        self.assertEqual(first["assumption_references"],17)
        self.assertEqual(first["independently_verified_assumptions"],0)
        self.assertEqual(first["modeled_pre_payment_exposure_cents"],0)
        self.assertEqual(first["modeled_probability_adjusted_net_cents"],12000)
        self.assertEqual(first["hypothetical_received_cents"],20000)
        self.assertEqual(first["hypothetical_outstanding_cents"],0)
        self.assertEqual(first["hypothetical_protected_reserve_cents"],5000)
        self.assertEqual(first["hypothetical_reinvestment_cents"],15000)
        for step in ("CAPABILITY_FOCUS","COUNCIL_MISSING_EVIDENCE","COUNCIL_REVIEW_ONLY",
                     "ACTUAL_LOCAL_ARTIFACT","NO_OVERWRITE","DUPLICATE_AND_OVERPAYMENT_DENIED",
                     "VERIFIED_BACKUP_RESTORE","RESTART_REQUIRES_RESUME","DURABLE_COUNCIL_AUDIT","DURABLE_OBLIGATION_AND_RECEIPTS",
                     "FUTURE_RECEIPT_EXCLUDED","PROTECTED_RESERVE_MODEL","FINAL_LEDGER_STABLE"):
            self.assertIn(step,first["checks"])
        for flag in ("buyer_accepted","contract_awarded","invoice_issued","payment_received",
                     "revenue_realized","funds_available","zero_capital_verified","external_authority",
                     "execution_eligible","reinvestment_authorized","release_eligible"):
            self.assertIs(first[flag],False)
        self.assertEqual(first["report_sha256"],
            _digest(_json({k:v for k,v in first.items() if k!="report_sha256"})))

    def test_requires_exact_confirmation_before_filesystem(self):
        with patch("nexus_exchange.genesis_diagnostic.TemporaryDirectory") as directory:
            for value in (None,False,1,"true"):
                with self.assertRaises(PermissionError):
                    run_diagnostic(confirmed=value)
            directory.assert_not_called()

    def test_failure_cleans_isolated_directory_and_withholds_report(self):
        created=[]
        def scratch(*args,**kwargs):
            result=TemporaryDirectory(*args,**kwargs)
            created.append(Path(result.name))
            return result
        with patch("nexus_exchange.genesis_diagnostic.TemporaryDirectory",side_effect=scratch), \
             patch("nexus_exchange.csv_workspace.CsvWorkspace.export",side_effect=ValueError("owned fixture failure")):
            with self.assertRaisesRegex(ValueError,"owned fixture failure"):
                run_diagnostic(confirmed=True)
        self.assertEqual(len(created),1)
        self.assertFalse(created[0].exists())


if __name__=="__main__":
    unittest.main()
