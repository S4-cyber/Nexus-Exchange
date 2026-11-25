import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from nexus_exchange.evidence import fingerprint,verify_reference,parse_reference,EvidenceError,MAX_BYTES
from nexus_exchange.checklist_store import ChecklistStore,context_for
from nexus_exchange.lead_store import LeadStore
from test_lead_store import reports,NOW
from test_owner_profile import profile

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory=Path(folder.name)
        self.path=self.directory/"synthetic-private-name.txt"
        self.content=b"synthetic notice section 2"
        self.path.write_bytes(self.content)

    def test_fingerprint_and_canonical_reference(self):
        ref=fingerprint(self.path,halted=False)
        digest=hashlib.sha256(self.content).hexdigest()
        self.assertEqual(ref,f"sha256:{digest};bytes:{len(self.content)}")
        self.assertEqual(parse_reference(ref),(digest,len(self.content)))
        self.assertNotIn(self.path.name,ref)
        self.assertNotIn(str(self.directory),ref)

    def test_match_and_mismatch_never_authorize(self):
        ref=fingerprint(self.path,halted=False)
        for expected in (True,False):
            result=verify_reference(self.path,ref,halted=False)
            self.assertEqual(result["byte_match"],expected)
            self.assertEqual(result["status"],"BYTE_MATCH" if expected else "BYTE_MISMATCH")
            self.assertFalse(result["independently_verified"])
            self.assertFalse(result["execution_eligible"])
            self.assertFalse(result["external_authority"])
            self.assertNotIn(self.path.name,str(result))
            self.path.write_bytes(b"modified")

    def test_halt_precedes_file_access(self):
        with patch("nexus_exchange.evidence.os.open") as opened:
            for state in (None,True,0):
                with self.assertRaises(PermissionError):
                    fingerprint(self.path,halted=state)
            with self.assertRaises(PermissionError):
                fingerprint(self.path,halted=False,halt_check=lambda:True)
            opened.assert_not_called()

    def test_halt_during_read(self):
        with self.assertRaises(PermissionError):
            fingerprint(self.path,halted=False,halt_check=Mock(side_effect=[False,True]))

    def test_invalid_reference_precedes_read(self):
        for bad in ("note","sha256:"+"A"*64+";bytes:2",
                "sha256:"+"0"*64+";bytes:00","sha256:"+"0"*64+";bytes:0",
                "sha256:"+"0"*64+";bytes:"+str(MAX_BYTES+1),None):
            with patch("nexus_exchange.evidence.os.open") as opened:
                with self.assertRaises(EvidenceError):
                    verify_reference(self.path,bad,halted=False)
                opened.assert_not_called()

    def test_bounded_regular_file_and_missing(self):
        for value in (self.directory,self.directory/"missing","relative.txt","//server/share/file"):
            with self.assertRaises(EvidenceError) as error:
                fingerprint(value,halted=False)
            self.assertNotIn(str(self.directory),str(error.exception))
        self.path.write_bytes(b"")
        with self.assertRaises(EvidenceError):
            fingerprint(self.path,halted=False)
        with self.path.open("wb") as f:
            f.truncate(MAX_BYTES+1)
        with self.assertRaises(EvidenceError):
            fingerprint(self.path,halted=False)

    def test_symlink_not_followed(self):
        link=self.directory/"link"
        try:
            link.symlink_to(self.path)
        except (OSError,NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(EvidenceError):
            fingerprint(link,halted=False)

    def test_file_replaced_or_changed_while_reading(self):
        actual=os.read
        changed=False
        def read(fd,size):
            nonlocal changed
            value=actual(fd,size)
            if not changed:
                changed=True
                with self.path.open("ab") as f:
                    f.write(b"change")
            return value
        with patch("nexus_exchange.evidence.os.read",side_effect=read):
            with self.assertRaisesRegex(EvidenceError,"CHANGED"):
                fingerprint(self.path,halted=False)

    def test_same_bytes_different_path(self):
        other=self.directory/"other.txt"
        other.write_bytes(self.content)
        ref=fingerprint(self.path,halted=False)
        self.assertTrue(verify_reference(other,ref,halted=False)["byte_match"])

    def test_existing_checklist_persistence_and_scope(self):
        ref=fingerprint(self.path,halted=False)
        with LeadStore(":memory:") as leads:
            leads.record(reports()[0],now=NOW,halted=False)
            row=leads.browse(now=NOW,source="sam",profile=profile(),halted=False)["leads"][0]
        context=context_for(row)
        database=self.directory/"todo.sqlite3"
        with ChecklistStore(database) as todo:
            todo.save(context,"source","evidence_noted",ref,now=NOW,expected_revision=None,halted=False)
        with ChecklistStore(database) as todo:
            result=todo.load(context,halted=False)
            saved=result["tasks"][0]["reference"]
            self.assertEqual(saved,ref)
            self.assertTrue(verify_reference(self.path,saved,halted=False)["byte_match"])
            self.assertFalse(result["independent_verification_complete"])
            self.assertFalse(result["external_authority"])
