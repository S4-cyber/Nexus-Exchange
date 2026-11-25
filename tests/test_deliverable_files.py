import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from datetime import timedelta

import test_digital_deliverable as prior
from nexus_exchange.digital_deliverable import DeliverableError, MAX_INPUT_BYTES
from nexus_exchange.deliverable_files import read_selected_csv,publish_new_csv,preview_pins
from nexus_exchange.csv_workspace import CsvWorkspace
from nexus_exchange.owner_profile import ProfileStore
from test_owner_profile import profile


class DeliverableFilesTests(unittest.TestCase):
    def setUp(self):
        # Real saved scenario, owner profile, archive and RuntimeGuard from
        # the verified prior fixture; do not duplicate its test discovery.
        self.fixture=prior.DigitalDeliverableTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.guard=self.fixture.guard
        self.directory=self.fixture.directory
        self.source=self.directory/"input.csv"
        self.source.write_bytes(prior.RAW)
        self.dest=self.directory/"output.csv"
        self.workspace=CsvWorkspace(self.fixture.key,action=self.guard.csv_file_action,
                                    blocked_check=self.guard.is_set)

    def preview(self):
        return self.workspace.preview(self.source,"id,name,category","id","2")

    def test_real_preview_and_exclusive_export(self):
        result=self.preview()
        self.assertFalse(self.dest.exists())
        self.assertEqual(result["artifact"],prior.EXPECTED)
        published=self.workspace.export(self.dest,confirmed=True)
        self.assertTrue(published["exported"])
        self.assertFalse(published["buyer_accepted"])
        self.assertEqual(self.dest.read_bytes(),prior.EXPECTED)
        self.assertFalse(self.workspace.ready)
        self.assertFalse(list(self.directory.glob(".nexus-csv-*.tmp")))

    def test_existing_destination_and_source_never_replaced(self):
        self.dest.write_bytes(b"existing")
        for path in (self.dest,self.source):
            self.preview()
            with self.assertRaisesRegex(DeliverableError,"DESTINATION_EXISTS"):
                self.workspace.export(path,confirmed=True)
        self.assertEqual(self.dest.read_bytes(),b"existing")
        self.assertEqual(self.source.read_bytes(),prior.RAW)

    def test_changed_source_after_preview_denied(self):
        self.preview()
        self.source.write_bytes(prior.RAW.replace(b"Alpha",b"Gamma"))
        with self.assertRaises(ValueError):
            self.workspace.export(self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.workspace.ready)

    def test_changed_profile_after_preview_denied(self):
        self.preview()
        with ProfileStore(self.directory/"owner-profile.sqlite3") as store:
            store.save(profile(hours_per_week=30),halted=False)
        with self.assertRaises(ValueError):
            self.workspace.export(self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())

    def test_halt_and_confirmation(self):
        self.preview()
        with self.assertRaises(PermissionError):
            self.workspace.export(self.dest,confirmed=1)
        self.guard.set()
        with self.assertRaises(PermissionError):
            self.workspace.export(self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.workspace.ready)

    def test_invalid_file_and_bounded_read(self):
        for path in (Path("relative.csv"),self.directory/"not.txt",self.directory/"missing.csv"):
            with self.assertRaises(DeliverableError):
                read_selected_csv(path,halted=False)
        self.source.write_bytes(b"x"*(MAX_INPUT_BYTES+1))
        with self.assertRaises(DeliverableError):
            read_selected_csv(self.source,halted=False)

    def test_bad_preview_pins_and_schema_before_read(self):
        with patch("nexus_exchange.deliverable_files.read_selected_csv") as reader:
            with self.assertRaises(ValueError):
                self.guard.csv_file_action("preview",self.fixture.key,confirmed=True,
                    source_path=self.source,columns=["id","id"],key_column="id",expected_rows=2)
            reader.assert_not_called()
        preview=self.preview()
        pins=preview_pins(preview)
        pins["expected_artifact"]="0"*64
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("export",self.fixture.key,confirmed=True,
                source_path=self.source,columns=["id","name","category"],key_column="id",
                expected_rows=2,destination_path=self.dest,**pins)
        self.assertFalse(self.dest.exists())

    def test_racing_destination_not_replaced_and_temp_cleaned(self):
        def race(src,dst):
            Path(dst).write_bytes(b"racer")
            raise FileExistsError()
        with patch("nexus_exchange.deliverable_files.os.link",side_effect=race):
            with self.assertRaisesRegex(DeliverableError,"DESTINATION_EXISTS"):
                publish_new_csv(self.dest,prior.EXPECTED,halted=False)
        self.assertEqual(self.dest.read_bytes(),b"racer")
        self.assertFalse(list(self.directory.glob(".nexus-csv-*.tmp")))

    def test_halt_before_publication_cleans_temp(self):
        states=iter([False,False,True])
        with self.assertRaises(PermissionError):
            publish_new_csv(self.dest,prior.EXPECTED,halted=False,halt_check=lambda:next(states,True))
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.directory.glob(".nexus-csv-*.tmp")))

    def test_no_overwrite_fallback_when_links_unsupported(self):
        with patch("nexus_exchange.deliverable_files.os.link",side_effect=OSError("synthetic")):
            with self.assertRaises(DeliverableError):
                publish_new_csv(self.dest,prior.EXPECTED,halted=False)
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.directory.glob(".nexus-csv-*.tmp")))

    def test_unknown_action_and_export_without_preview(self):
        with self.assertRaises(ValueError):
            self.guard.csv_file_action("send",self.fixture.key,confirmed=True)
        with self.assertRaises(PermissionError):
            self.workspace.export(self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())

if __name__=="__main__":
    unittest.main()
