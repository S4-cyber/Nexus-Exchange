import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nexus_exchange.database_backup import create_backup,restore_backup,verify_backup,MANIFEST
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.owner_profile import ProfileStore
from test_owner_profile import profile


class DatabaseBackupTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.source=self.root/"original"
        self.backup=self.root/"backup"
        self.dest=self.root/"restored"
        self.now=datetime(2026,11,24,12,tzinfo=timezone.utc)
        self.clock=lambda:self.now
        with RuntimeGuard(self.source,clock=self.clock) as guard:
            guard.resume()
            with ProfileStore(self.source/"owner-profile.sqlite3") as store:
                store.save(profile(),halted=False)
        (self.source/"external-evidence.txt").write_bytes(b"owned synthetic private file")

    def create(self,**changes):
        args=dict(confirmed=True)
        args.update(changes)
        return create_backup(self.source,self.backup,**args)

    def test_real_backup_restore_and_startup_halted(self):
        original=(self.source/"events.sqlite3").read_bytes()
        result=self.create()
        self.assertEqual(verify_backup(self.backup),result)
        self.assertEqual([r["name"] for r in result["files"]],
                         ["events.sqlite3","owner-profile.sqlite3"])
        self.assertFalse(result["encrypted"])
        self.assertFalse(result["external_authority"])
        restored=restore_backup(self.backup,self.dest,confirmed=True)
        self.assertEqual(restored["restored_files"],2)
        self.assertFalse(restored["automatic_resume"])
        self.assertFalse((self.dest/"external-evidence.txt").exists())
        self.assertFalse((self.dest/"runtime.lock").exists())
        self.assertEqual((self.dest/"events.sqlite3").read_bytes(),original)
        self.assertEqual((self.source/"events.sqlite3").read_bytes(),original)
        self.now+=timedelta(seconds=1)
        with RuntimeGuard(self.dest,clock=self.clock) as guard:
            self.assertTrue(guard.is_set())
            guard.resume()
            with ProfileStore(self.dest/"owner-profile.sqlite3") as store:
                self.assertEqual(store.load(halted=False),profile())

    def test_confirmation_denied_before_destination(self):
        for value in (None,False,1,"true"):
            with self.assertRaises(PermissionError):
                self.create(confirmed=value)
        self.assertFalse(self.backup.exists())
        self.create()
        with self.assertRaises(PermissionError):
            restore_backup(self.backup,self.dest,confirmed=False)
        self.assertFalse(self.dest.exists())

    def test_running_instance_denied_even_halted(self):
        with RuntimeGuard(self.source,clock=self.clock):
            with self.assertRaises(PermissionError):
                self.create()
        self.assertFalse(self.backup.exists())

    def test_existing_destination_and_nested_paths_denied(self):
        self.backup.mkdir()
        sentinel=self.backup/"sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(sentinel.read_bytes(),b"keep")
        with self.assertRaises(ValueError):
            create_backup(self.source,self.source/"nested",confirmed=True)

    def test_unknown_database_and_sidecar_denied(self):
        for name in ("events.sqlite3-wal","unknown.db","events.sqlite3-journal"):
            path=self.source/name
            path.write_bytes(b"fixture")
            with self.assertRaises(ValueError):
                self.create()
            path.unlink()
        self.assertFalse(self.backup.exists())

    def test_corruption_and_extra_file_rejected_before_restore(self):
        self.create()
        file=self.backup/"owner-profile.sqlite3"
        original=file.read_bytes()
        file.write_bytes(original+b"x")
        with self.assertRaises(ValueError):
            restore_backup(self.backup,self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())
        file.write_bytes(original)
        (self.backup/"extra.txt").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            verify_backup(self.backup)

    def test_failed_copy_removes_only_new_owned_files(self):
        with patch("nexus_exchange.database_backup._copy_new",side_effect=OSError("synthetic write error")):
            with self.assertRaises(OSError):
                self.create()
        self.assertFalse(self.backup.exists())
        self.assertTrue((self.source/"external-evidence.txt").exists())

    def test_rejects_non_shutdown_runtime(self):
        import sqlite3
        db=sqlite3.connect(self.source/"events.sqlite3")
        try:
            db.execute("UPDATE runtime_guard_v1 SET state='offline_ready', reason='explicit_resume'")
            db.commit()
        finally:
            db.close()
        with self.assertRaises(ValueError):
            self.create()
        self.assertFalse(self.backup.exists())

    def test_malformed_manifest_and_no_restore_overwrite(self):
        self.create()
        self.dest.mkdir()
        (self.dest/"sentinel").write_bytes(b"existing")
        with self.assertRaises(ValueError):
            restore_backup(self.backup,self.dest,confirmed=True)
        self.assertEqual((self.dest/"sentinel").read_bytes(),b"existing")
        (self.backup/MANIFEST).write_bytes(b'{"x":1,"x":2}\n')
        with self.assertRaises(ValueError):
            verify_backup(self.backup)


if __name__=="__main__":
    unittest.main()
