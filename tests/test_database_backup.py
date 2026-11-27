import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nexus_exchange.database_backup import create_backup,restore_backup,verify_backup,MANIFEST
from nexus_exchange.runtime_guard import RuntimeGuard
from nexus_exchange.owner_profile import ProfileStore, normalize_profile
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
                self.assertEqual(store.load(halted=False),normalize_profile(profile()))

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


    def test_v2_exact_report_bytes_and_declared_build(self):
        import json
        from hashlib import sha256
        from nexus_exchange.cycle_history import BRIEF
        raw=json.dumps(dict(format="nexus-engagement-brief-v1",status="completed",
                            finished=self.now.isoformat(),jobs={},notes=["é"],
                            shortlist=[],sources=[]),ensure_ascii=False).encode("utf-16")
        (self.source/BRIEF).write_bytes(raw)
        result=self.create(build_id="a"*40)
        self.assertEqual(result["application_commit_asserted"],"a"*40)
        self.assertTrue(result["latest_report_present"])
        self.assertEqual(result["format"],"nexus-local-database-backup-v2")
        row=next(r for r in result["files"] if r["name"]==BRIEF)
        self.assertEqual(row["sha256"],sha256(raw).hexdigest())
        self.assertEqual(verify_backup(self.backup),result)
        restore_backup(self.backup,self.dest,confirmed=True)
        self.assertEqual((self.dest/BRIEF).read_bytes(),raw)
        self.assertEqual((self.source/BRIEF).read_bytes(),raw)

    def test_v2_absent_report_and_bad_build_id(self):
        for value in ("",True,"A"*40,"a"*39):
            with self.assertRaises(ValueError):
                self.create(build_id=value)
        self.assertFalse(self.backup.exists())
        result=self.create(build_id="b"*40)
        self.assertFalse(result["latest_report_present"])
        self.assertEqual(verify_backup(self.backup),result)

    def test_v2_invalid_report_preserves_original(self):
        from nexus_exchange.cycle_history import BRIEF
        path=self.source/BRIEF
        path.write_bytes(b'{"invalid":true}')
        with self.assertRaises(ValueError):
            self.create(build_id="c"*40)
        self.assertFalse(self.backup.exists())
        self.assertEqual(path.read_bytes(),b'{"invalid":true}')

    def test_v2_report_tampering_rejected_before_restore(self):
        import json
        from nexus_exchange.cycle_history import BRIEF
        raw=json.dumps(dict(format="nexus-engagement-brief-v1",status="completed",
                            finished=self.now.isoformat(),jobs={},notes=[],
                            shortlist=[],sources=[])).encode()
        (self.source/BRIEF).write_bytes(raw)
        self.create(build_id="d"*40)
        (self.backup/BRIEF).write_bytes(raw+b" ")
        with self.assertRaises(ValueError):
            restore_backup(self.backup,self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())

    def test_v1_report_exclusion_remains_explicit(self):
        from nexus_exchange.cycle_history import BRIEF
        (self.source/BRIEF).write_bytes(b"legacy excluded bytes")
        result=self.create()
        self.assertEqual(result["kind"],"LOCAL_DATABASES_ONLY")
        self.assertFalse((self.backup/BRIEF).exists())



    def test_v2_semantically_invalid_journal_rejected_without_source_change(self):
        import json
        import sqlite3
        from contextlib import closing
        path=self.source/"events.sqlite3"
        # Valid SQLite pages, but a terminal event without a predecessor.
        with closing(sqlite3.connect(path)) as db:
            db.execute("INSERT INTO events(payload) VALUES (?)", (json.dumps(
                dict(task_id="orphan",target="synthetic",state="succeeded",
                     timestamp=self.now.isoformat())),))
            db.commit()
        original=path.read_bytes()
        with self.assertRaisesRegex(ValueError,"invalid transition"):
            self.create(build_id="e"*40)
        self.assertFalse(self.backup.exists())
        self.assertEqual(path.read_bytes(),original)

    def test_v2_rehashed_invalid_journal_rejected_on_verify_and_restore(self):
        import json
        import sqlite3
        from contextlib import closing
        from hashlib import sha256
        from nexus_exchange.database_backup import _manifest, _json
        manifest=self.create(build_id="f"*40)
        path=self.backup/"events.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.execute("INSERT INTO events(payload) VALUES (?)", (json.dumps(
                dict(task_id="orphan",target="synthetic",state="succeeded",
                     timestamp=self.now.isoformat())),))
            db.commit()
        raw=path.read_bytes()
        files=[dict(row,bytes=len(raw),sha256=sha256(raw).hexdigest())
               if row["name"]=="events.sqlite3" else row for row in manifest["files"]]
        updated=_manifest(files,manifest["runtime_state"],"f"*40)
        (self.backup/MANIFEST).write_bytes((_json(updated)+"\n").encode("ascii"))
        with self.assertRaisesRegex(ValueError,"invalid transition"):
            verify_backup(self.backup)
        with self.assertRaisesRegex(ValueError,"invalid transition"):
            restore_backup(self.backup,self.dest,confirmed=True)
        self.assertFalse(self.dest.exists())
        self.assertEqual(path.read_bytes(),raw)

    def test_v2_abrupt_owner_exit_recovery_then_restore_stays_halted(self):
        import subprocess
        import sys
        from nexus_exchange.cycle_history import BRIEF
        from nexus_exchange.dashboard_events import project
        script=(
            "from nexus_exchange.runtime_guard import RuntimeGuard\n"
            "from nexus_exchange.cycle_history import BRIEF\n"
            "from datetime import datetime, timezone\n"
            "from pathlib import Path\n"
            "import json, os, sys\n"
            "n=datetime(2026,11,24,12,tzinfo=timezone.utc)\n"
            "g=RuntimeGuard(sys.argv[1],clock=lambda:n)\n"
            "g.resume()\n"
            "for state in ('queued','running'):\n"
            "    g.events.append(dict(task_id='a'*32,target='Autonomous Scout cycle',"
            "state=state,timestamp=n.isoformat()))\n"
            "raw=json.dumps(dict(format='nexus-engagement-brief-v1',status='completed',"
            "cycle_id='a'*32,finished=n.isoformat(),jobs={},notes=[],shortlist=[],sources=[])).encode()\n"
            "with (Path(sys.argv[1])/BRIEF).open('wb') as handle:\n"
            "    handle.write(raw); handle.flush(); os.fsync(handle.fileno())\n"
            "os._exit(17)\n"
        )
        result=subprocess.run([sys.executable,"-c",script,str(self.source)],
                              capture_output=True,timeout=30)
        self.assertEqual(result.returncode,17,result.stderr.decode(errors="replace"))
        original=(self.source/BRIEF).read_bytes()
        with self.assertRaises(ValueError):
            self.create(build_id="1"*40)
        self.assertFalse(self.backup.exists())
        self.now+=timedelta(seconds=1)
        with RuntimeGuard(self.source,clock=self.clock) as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.recovered_count,1)
            view=project(guard.events.read())
            self.assertEqual(view["history"][-1].state,"interrupted")
            self.assertEqual(view["successful_tasks"],0)
        self.create(build_id="1"*40)
        restore_backup(self.backup,self.dest,confirmed=True)
        self.assertEqual((self.dest/BRIEF).read_bytes(),original)
        self.now+=timedelta(seconds=1)
        with RuntimeGuard(self.dest,clock=self.clock) as guard:
            self.assertTrue(guard.is_set())
            self.assertEqual(guard.recovered_count,0)
            view=project(guard.events.read())
            self.assertEqual(len(view["history"]),3)
            self.assertEqual(view["history"][-1].state,"interrupted")
            self.assertEqual(view["successful_tasks"],0)
            self.assertFalse(guard.status()["external_authority"])


    def test_v2_archive_validation_on_create_verify_and_restore(self):
        import sqlite3
        from contextlib import closing
        from hashlib import sha256
        from nexus_exchange.cycle_history import CycleHistory, encode
        from nexus_exchange.database_backup import _manifest, _json
        original = self.source / "events.sqlite3"
        brief = dict(format="nexus-engagement-brief-v1", status="Completed",
                     finished=self.now.isoformat(), jobs={}, notes=[], shortlist=[], sources=[])
        body = encode(brief)
        with closing(sqlite3.connect(original)) as db:
            CycleHistory(db)
            db.execute("INSERT INTO cycle_briefs VALUES (?,?,?,?)",
                       (sha256(body).hexdigest(), brief["finished"], brief["status"], body))
            db.execute("UPDATE cycle_briefs SET status='forged'")
            db.commit()
        damaged = original.read_bytes()
        with self.assertRaisesRegex(ValueError, "metadata mismatch"):
            self.create(build_id="2"*40)
        self.assertFalse(self.backup.exists())
        self.assertEqual(original.read_bytes(), damaged)
        with closing(sqlite3.connect(original)) as db:
            db.execute("UPDATE cycle_briefs SET status='Completed'")
            db.commit()
        manifest = self.create(build_id="2"*40)
        self.assertEqual(verify_backup(self.backup), manifest)
        restore_backup(self.backup, self.dest, confirmed=True)
        self.assertEqual((self.dest / "events.sqlite3").read_bytes(), original.read_bytes())
        damaged_backup = self.backup / "events.sqlite3"
        with closing(sqlite3.connect(damaged_backup)) as db:
            db.execute("UPDATE cycle_briefs SET status='forged'")
            db.commit()
        raw = damaged_backup.read_bytes()
        files = [dict(row, bytes=len(raw), sha256=sha256(raw).hexdigest())
                 if row["name"] == "events.sqlite3" else row for row in manifest["files"]]
        updated = _manifest(files, manifest["runtime_state"], "2"*40)
        (self.backup / MANIFEST).write_bytes((_json(updated)+"\n").encode("ascii"))
        with self.assertRaisesRegex(ValueError, "metadata mismatch"):
            verify_backup(self.backup)
        other = self.root / "rejected"
        with self.assertRaisesRegex(ValueError, "metadata mismatch"):
            restore_backup(self.backup, other, confirmed=True)
        self.assertFalse(other.exists())
        self.assertEqual(damaged_backup.read_bytes(), raw)


    def test_v2_advisory_ledger_semantics_and_preservation(self):
        import sqlite3
        from contextlib import closing
        from hashlib import sha256
        from nexus_exchange.advisory_attempts import AdvisoryAttemptStore
        from nexus_exchange.advisory_process import FIXTURE_MODEL_SHA256
        from nexus_exchange.database_backup import _manifest, _json
        from test_context_packet import snapshot, NOW

        name = "local-advisory.sqlite3"
        path = self.source / name
        original = snapshot()
        with AdvisoryAttemptStore(path) as store:
            store.reserve(original, FIXTURE_MODEL_SHA256, now=NOW,
                          approved=True, halted=False)
        valid = path.read_bytes()
        with closing(sqlite3.connect(path)) as db:
            db.execute("UPDATE advisory_attempts_v1 SET payload='{}'")
            db.commit()
        damaged = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "advisory ledger"):
            self.create(build_id="3"*40)
        self.assertFalse(self.backup.exists())
        self.assertEqual(path.read_bytes(), damaged)
        path.write_bytes(valid)
        manifest = self.create(build_id="3"*40)
        restore_backup(self.backup, self.dest, confirmed=True)
        self.assertEqual((self.dest / name).read_bytes(), valid)
        with AdvisoryAttemptStore(self.dest / name, existing_only=True) as store:
            self.assertEqual(store.status(original["plan_id"], halted=False)["state"], "RESERVED")
        target = self.backup / name
        with closing(sqlite3.connect(target)) as db:
            db.execute("UPDATE advisory_attempts_v1 SET payload='{}'")
            db.commit()
        raw = target.read_bytes()
        files = [dict(row, bytes=len(raw), sha256=sha256(raw).hexdigest())
                 if row["name"] == name else row for row in manifest["files"]]
        updated = _manifest(files, manifest["runtime_state"], "3"*40)
        (self.backup / MANIFEST).write_bytes((_json(updated)+"\n").encode("ascii"))
        with self.assertRaisesRegex(ValueError, "advisory ledger"):
            verify_backup(self.backup)
        rejected = self.root / "rejected"
        with self.assertRaisesRegex(ValueError, "advisory ledger"):
            restore_backup(self.backup, rejected, confirmed=True)
        self.assertFalse(rejected.exists())
        self.assertEqual(target.read_bytes(), raw)

    def test_v2_launch_marker_preserved_and_malformed_rejected(self):
        import sqlite3
        from contextlib import closing
        path = self.source / "events.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.execute("INSERT INTO advisory_launch_v1 VALUES (1,?)", ("a"*64,))
            db.commit()
        manifest = self.create(build_id="4"*40)
        self.assertEqual(verify_backup(self.backup), manifest)
        restore_backup(self.backup, self.dest, confirmed=True)
        self.assertEqual((self.dest / "events.sqlite3").read_bytes(), path.read_bytes())
        with closing(sqlite3.connect(path)) as db:
            db.execute("UPDATE advisory_launch_v1 SET reservation_id='broken'")
            db.commit()
        invalid = path.read_bytes()
        rejected = self.root / "bad-marker"
        with self.assertRaisesRegex(ValueError, "advisory launch"):
            create_backup(self.source, rejected, confirmed=True, build_id="4"*40)
        self.assertFalse(rejected.exists())
        self.assertEqual(path.read_bytes(), invalid)

    def test_v2_marker_trigger_rejected_on_create_verify_and_restore(self):
        import sqlite3
        from contextlib import closing
        from hashlib import sha256
        from nexus_exchange.database_backup import _manifest, _json
        name = "events.sqlite3"
        path = self.source / name
        trigger = ("CREATE TRIGGER broken AFTER INSERT ON advisory_launch_v1 "
                   "BEGIN DELETE FROM advisory_launch_v1; END")
        with closing(sqlite3.connect(path)) as db:
            db.execute(trigger)
            db.commit()
        damaged = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "advisory launch trigger"):
            self.create(build_id="5"*40)
        self.assertFalse(self.backup.exists())
        self.assertEqual(path.read_bytes(), damaged)
        with closing(sqlite3.connect(path)) as db:
            db.execute("DROP TRIGGER broken")
            db.commit()
        manifest = self.create(build_id="5"*40)
        target = self.backup / name
        with closing(sqlite3.connect(target)) as db:
            db.execute(trigger)
            db.commit()
        raw = target.read_bytes()
        files = [dict(row, bytes=len(raw), sha256=sha256(raw).hexdigest())
                 if row["name"] == name else row for row in manifest["files"]]
        updated = _manifest(files, manifest["runtime_state"], "5"*40)
        (self.backup / MANIFEST).write_bytes((_json(updated)+"\n").encode("ascii"))
        with self.assertRaisesRegex(ValueError, "advisory launch trigger"):
            verify_backup(self.backup)
        with self.assertRaisesRegex(ValueError, "advisory launch trigger"):
            restore_backup(self.backup, self.dest, confirmed=True)
        self.assertFalse(self.dest.exists())
        self.assertEqual(target.read_bytes(), raw)

if __name__=="__main__":
    unittest.main()
