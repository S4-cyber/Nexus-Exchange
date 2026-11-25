import copy
import unittest
from unittest.mock import Mock

import test_deliverable_obligations as prior
from nexus_exchange.csv_workspace import CsvWorkspace
from nexus_exchange.obligation_workspace import ObligationWorkspace,validate_record,record_text
from nexus_exchange.deliverable_obligations import NOTE_KINDS


class ObligationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=prior.ObligationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.plan=self.fixture.plan
        self.busy=False
        self.csv=CsvWorkspace(self.plan,action=self.guard.csv_file_action,
                              blocked_check=lambda:self.busy or self.guard.is_set())
        self.ledger=ObligationWorkspace(self.plan,action=self.guard.csv_obligation_action,
                                       blocked_check=lambda:self.busy or self.guard.is_set())

    def register(self):
        self.csv.preview(self.fixture.source,"id,name,category","id","2")
        return self.csv.register(self.fixture.artifact,confirmed=True)

    def test_native_controller_register_inspect_note_history(self):
        record=self.register()
        self.assertFalse(self.csv.ready)
        self.assertFalse(record["buyer_accepted"])
        listing=self.ledger.refresh()
        self.assertEqual(listing["rows"],[record])
        self.assertIsNone(self.ledger.selected)
        self.assertEqual(self.ledger.inspect(record["obligation_id"]),record)
        current=self.ledger.note(NOTE_KINDS[0],self.fixture.evidence,confirmed=True)
        self.assertEqual(len(current["notes"]),1)
        self.assertFalse(current["invoice_eligible"])
        self.assertIn("Acceptance claim — unverified",record_text(current))
        self.assertEqual(self.ledger.inspect(record["obligation_id"]),current)

    def test_register_requires_exact_confirmed_preview(self):
        with self.assertRaises(PermissionError):
            self.csv.register(self.fixture.artifact,confirmed=True)
        self.csv.preview(self.fixture.source,"id,name,category","id","2")
        with self.assertRaises(PermissionError):
            self.csv.register(self.fixture.artifact,confirmed=1)
        self.fixture.artifact.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.csv.register(self.fixture.artifact,confirmed=True)
        self.assertFalse(self.csv.ready)

    def test_busy_and_halt_clear_selected(self):
        record=self.register()
        self.ledger.inspect(record["obligation_id"])
        self.busy=True
        with self.assertRaises(PermissionError):
            self.ledger.note(NOTE_KINDS[0],self.fixture.evidence,confirmed=True)
        self.assertIsNone(self.ledger.selected)
        self.busy=False
        self.ledger.inspect(record["obligation_id"])
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.ledger.refresh()
        self.assertIsNone(self.ledger.selected)

    def test_stale_head_note_requires_reinspect(self):
        record=self.register()
        self.ledger.inspect(record["obligation_id"])
        self.fixture.note(record)
        self.fixture.evidence.write_bytes(b"new evidence fixture")
        with self.assertRaises(ValueError):
            self.ledger.note(NOTE_KINDS[1],self.fixture.evidence,confirmed=True)
        self.assertIsNone(self.ledger.selected)
        self.ledger.inspect(record["obligation_id"])
        result=self.ledger.note(NOTE_KINDS[1],self.fixture.evidence,confirmed=True)
        self.assertEqual(len(result["notes"]),2)

    def test_validation_rejects_scope_authority_and_chain_drift(self):
        record=self.register()
        current=self.fixture.note(record)
        variants=[dict(current,plan_id="0"*64),dict(current,buyer_accepted=True),
                  dict(current,head_sha256="0"*64),dict(current,registration_sha256="0"*64)]
        corrupted=copy.deepcopy(current)
        corrupted["notes"][0]["reference"]="sha256:"+"0"*64+";bytes:1"
        variants.append(corrupted)
        for variant in variants:
            with self.assertRaises(ValueError):
                validate_record(variant,self.plan)

    def test_refresh_rejects_duplicate_records_and_clears_selection(self):
        record=self.register()
        self.ledger.inspect(record["obligation_id"])
        result=self.ledger.refresh()
        result["rows"].append(copy.deepcopy(record))
        self.ledger.action=Mock(return_value=result)
        with self.assertRaises(ValueError):
            self.ledger.refresh()
        self.assertIsNone(self.ledger.selected)

    def test_result_withheld_on_post_call_halt(self):
        record=self.register()
        states=iter([False,True])
        workspace=ObligationWorkspace(self.plan,action=Mock(return_value=record),
                                      blocked_check=lambda:next(states,True))
        with self.assertRaises(PermissionError):
            workspace.inspect(record["obligation_id"])
        self.assertIsNone(workspace.selected)

    def test_selection_is_defensive_copy_and_confirmation_required(self):
        record=self.register()
        selected=self.ledger.inspect(record["obligation_id"])
        selected["buyer_accepted"]=True
        self.assertFalse(self.ledger.selected["buyer_accepted"])
        with self.assertRaises(PermissionError):
            self.ledger.note(NOTE_KINDS[0],self.fixture.evidence,confirmed=False)
        self.assertEqual(self.ledger.selected,record)


if __name__=="__main__":
    unittest.main()
