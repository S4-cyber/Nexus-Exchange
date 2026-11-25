"""Offline, closed-instance database backup and new-directory recovery.

Trusted cooperating local application/filesystem only. No network, encryption,
authenticity claim, live migration, overwrite, or automatic recovery/resume.
Explicitly excludes user-selected evidence files and exported artifacts.
"""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from .runtime_guard import _lock, MAX_REVISION
from .scout import _timestamp

FORMAT="nexus-local-database-backup-v1"
MANIFEST="BACKUP.json"
MAX_DB_BYTES=128*1024*1024
MAX_TOTAL_BYTES=512*1024*1024
MAX_MANIFEST_BYTES=16384
REQUIRED="events.sqlite3"
LOCK="runtime.lock"
# Required subset of tables, not a migration or exhaustive schema audit.
DATABASES={
    REQUIRED:("events","runtime_guard_v1"),
    "archive.sqlite3":("observations_v1",),
    "scout-leads.sqlite3":("scout_observations_v1",),
    "owner-profile.sqlite3":("owner_profile_v1",),
    "scout-todo.sqlite3":("scout_checklists_v1",),
    "council.sqlite3":("council_attempts_v1",),
    "operator.sqlite3":("operator_drafts_v1",),
    "operator-recipients.sqlite3":("operator_recipients_v1",),
    "operator-obligations.sqlite3":("csv_obligations_v1","csv_obligation_notes_v1"),
    "operator-simulated-invoices.sqlite3":("sim_invoices_v1","sim_receipts_v1"),
}
_FLAGS=("encrypted","publisher_authenticated","independently_verified",
        "production_ready","automatic_resume","external_authority")


def _confirm(value):
    if value is not True:
        raise PermissionError("explicit offline maintenance confirmation required")


def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)


def _digest(value):
    return sha256(_json(value).encode("ascii")).hexdigest()


def _pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError("duplicate backup metadata key")
        out[key]=value
    return out


def _no_constant(_):
    raise ValueError("invalid backup metadata constant")


def _path(value):
    try:
        raw=os.fspath(value)
        if (type(raw) is not str or not os.path.isabs(raw) or len(raw)>4096
                or raw.startswith(("//","\\\\")) or ".." in Path(raw).parts):
            raise ValueError()
        path=Path(raw)
        if os.name=="nt" and any(":" in part or Path(part).is_reserved()
                                  for part in path.parts[1:]):
            raise ValueError()
        # Resolve the existing parent but deny final links. This is not
        # protection from malicious ancestor swaps or mapped network drives.
        return path.parent.resolve(strict=True)/path.name
    except (OSError,ValueError,TypeError,OverflowError):
        raise ValueError("select an absolute trusted local directory") from None


def _directory(value):
    path=_path(value)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("existing local directory required")
    return path


def _destination(value,source):
    path=_path(value)
    if (path==source or source in path.parents or path in source.parents
            or os.path.lexists(path)):
        raise ValueError("select a distinct new sibling/external directory")
    return path


def _regular(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("regular local backup file required")
    return info


def _identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _scan(source,*,backup=False):
    """Reject known SQLite sidecars and unknown database-like names."""
    files=[]
    for entry in source.iterdir():
        name=entry.name
        lower=name.lower()
        if name in DATABASES:
            info=_regular(entry)
            if not 1<=info.st_size<=MAX_DB_BYTES:
                raise ValueError("database outside backup size bound")
            files.append(name)
        elif backup:
            if name!=MANIFEST:
                raise ValueError("unexpected file in backup directory")
        elif (lower.endswith((".sqlite",".sqlite3",".db",".db3","-wal","-shm","-journal"))
              or any(lower.startswith(n.lower()+"-") for n in DATABASES)):
            raise ValueError("unknown database or SQLite sidecar; close and review first")
    files.sort()
    if REQUIRED not in files:
        raise ValueError("runtime database required")
    return files


def _stream(path,maximum,*,output=None,retain=False):
    """Hash/copy regular bytes without following final links."""
    initial=_regular(path)
    if not 1<=initial.st_size<=maximum:
        raise ValueError("backup file outside size bound")
    flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or initial.st_size!=before.st_size
                or (initial.st_ino and before.st_ino and
                    (initial.st_dev,initial.st_ino)!=(before.st_dev,before.st_ino))):
            raise ValueError("backup file changed")
        digest=sha256()
        data=bytearray()
        size=0
        while True:
            block=os.read(fd,min(65536,maximum+1-size))
            if not block:
                break
            size+=len(block)
            if size>maximum:
                raise ValueError("backup file outside size bound")
            digest.update(block)
            if output is not None and output.write(block)!=len(block):
                raise OSError("short backup write")
            if retain:
                data.extend(block)
        if (size!=before.st_size or _identity(before)!=_identity(os.fstat(fd))
                or _identity(initial)!=_identity(_regular(path))):
            raise ValueError("backup file changed")
    finally:
        os.close(fd)
    return dict(bytes=size,sha256=digest.hexdigest()),bytes(data) if retain else None


def _state(raw):
    if (type(raw) is not dict or set(raw)!={"state","reason","revision","changed_at"}
            or raw["state"]!="halted" or raw["reason"]!="shutdown"
            or type(raw["revision"]) is not int or not 1<=raw["revision"]<=MAX_REVISION
            or type(raw["changed_at"]) is not str
            or _timestamp(raw["changed_at"]).isoformat(timespec="microseconds")!=raw["changed_at"]):
        raise ValueError("cleanly shut-down runtime required")
    return raw


def _database(path,name):
    """Read only, with no SQLite sidecars. Requires a closed trusted snapshot."""
    uri=path.resolve(strict=True).as_uri()+"?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA quick_check(1)").fetchall()!=[("ok",)]:
                raise ValueError("SQLite snapshot integrity failure")
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not set(DATABASES[name])<=tables:
                raise ValueError("SQLite snapshot schema mismatch")
            if name==REQUIRED:
                rows=db.execute("SELECT slot,state,reason,revision,changed_at FROM runtime_guard_v1").fetchall()
                if len(rows)!=1 or rows[0][0]!=1:
                    raise ValueError("invalid runtime state")
                return _state(dict(zip(("state","reason","revision","changed_at"),rows[0][1:])))
        finally:
            pass
    return None


def _manifest(files,state):
    if type(files) is not list or not 1<=len(files)<=len(DATABASES):
        raise ValueError("invalid backup file list")
    names=[]
    total=0
    for row in files:
        if (type(row) is not dict or set(row)!={"name","bytes","sha256"}
                or type(row["name"]) is not str or row["name"] not in DATABASES
                or type(row["bytes"]) is not int or not 1<=row["bytes"]<=MAX_DB_BYTES
                or type(row["sha256"]) is not str or not re.fullmatch("[0-9a-f]{64}",row["sha256"])):
            raise ValueError("invalid backup file descriptor")
        names.append(row["name"])
        total+=row["bytes"]
    if names!=sorted(set(names)) or REQUIRED not in names or total>MAX_TOTAL_BYTES:
        raise ValueError("invalid backup inventory")
    payload=dict(format=FORMAT,kind="LOCAL_DATABASES_ONLY",files=files,
                 total_bytes=total,runtime_state=_state(state),**dict.fromkeys(_FLAGS,False))
    return dict(payload,manifest_sha256=_digest(payload))


def _metadata(raw):
    try:
        data=json.loads(raw.decode("ascii"),object_pairs_hook=_pairs,parse_constant=_no_constant)
        if type(data) is not dict:
            raise ValueError()
        expected=_manifest(data.get("files"),data.get("runtime_state"))
        if (_json(expected)+"\n").encode("ascii")!=raw:
            raise ValueError()
        return expected
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise ValueError("invalid backup manifest") from None


def verify_backup(directory):
    """Verify exact known file inventory, hashes, SQLite and halted state."""
    path=_directory(directory)
    _,raw=_stream(path/MANIFEST,MAX_MANIFEST_BYTES,retain=True)
    manifest=_metadata(raw)
    if _scan(path,backup=True)!=[row["name"] for row in manifest["files"]]:
        raise ValueError("backup inventory mismatch")
    for row in manifest["files"]:
        observed,_=_stream(path/row["name"],MAX_DB_BYTES)
        if observed!={k:row[k] for k in ("bytes","sha256")}:
            raise ValueError("backup file digest mismatch")
        state=_database(path/row["name"],row["name"])
        if row["name"]==REQUIRED and state!=manifest["runtime_state"]:
            raise ValueError("backup halt state mismatch")
    return manifest


def _copy_new(source,destination,expected=None):
    """Create only a new file. Partial outputs are removed by the caller."""
    with destination.open("xb") as handle:
        observed,_=_stream(source,MAX_DB_BYTES,output=handle)
        handle.flush()
        os.fsync(handle.fileno())
    if expected is not None and observed!=expected:
        raise ValueError("snapshot changed since verification")
    return observed


def _cleanup(path,created):
    # Only unlink files created by this operation, never recursively delete.
    # Trusted local filesystem required; cleanup failure is surfaced.
    try:
        for item in reversed(created):
            item.unlink(missing_ok=True)
        path.rmdir()
    except OSError:
        raise ValueError("backup cleanup incomplete; inspect new directory") from None


def create_backup(source,destination,*,confirmed=None):
    _confirm(confirmed)
    source=_directory(source)
    destination=_destination(destination,source)
    _regular(source/LOCK)
    try:
        lock=_lock(source/LOCK)
    except OSError:
        raise PermissionError("close application before backup") from None
    created=[]
    try:
        names=_scan(source)
        state=_database(source/REQUIRED,REQUIRED)
        if sum(_regular(source/name).st_size for name in names)>MAX_TOTAL_BYTES:
            raise ValueError("backup total size limit")
        destination.mkdir(mode=0o700)
        try:
            files=[]
            for name in names:
                target=destination/name
                created.append(target)
                observed=_copy_new(source/name,target)
                if _database(target,name)!= (state if name==REQUIRED else None):
                    raise ValueError("copied runtime state mismatch")
                files.append(dict(name=name,**observed))
            if _scan(source)!=names or _database(source/REQUIRED,REQUIRED)!=state:
                raise ValueError("source inventory or shutdown state changed")
            # Rehash while holding the cooperative runtime lock.
            for row in files:
                observed,_=_stream(source/row["name"],MAX_DB_BYTES)
                if observed!={k:row[k] for k in ("bytes","sha256")}:
                    raise ValueError("source changed during backup")
            manifest=_manifest(files,state)
            target=destination/MANIFEST
            created.append(target)
            with target.open("xb") as handle:
                handle.write((_json(manifest)+"\n").encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
            return verify_backup(destination)
        except BaseException:
            _cleanup(destination,created)
            raise
    finally:
        lock.close()


def restore_backup(source,destination,*,confirmed=None):
    _confirm(confirmed)
    source=_directory(source)
    destination=_destination(destination,source)
    manifest=verify_backup(source)
    destination.mkdir(mode=0o700)
    created=[]
    try:
        for row in manifest["files"]:
            target=destination/row["name"]
            created.append(target)
            expected={k:row[k] for k in ("bytes","sha256")}
            _copy_new(source/row["name"],target,expected)
            state=_database(target,row["name"])
            if row["name"]==REQUIRED and state!=manifest["runtime_state"]:
                raise ValueError("restored halt state mismatch")
        if verify_backup(source)!=manifest or _scan(destination)!=[r["name"] for r in manifest["files"]]:
            raise ValueError("restore inventory changed")
        # Lock file is deliberately not copied; RuntimeGuard creates it on
        # first launch and persists halted startup before any operation.
        return dict(backup_manifest_sha256=manifest["manifest_sha256"],
                    restored_files=len(manifest["files"]),runtime_state=manifest["runtime_state"],
                    restored=True,**dict.fromkeys(_FLAGS,False))
    except BaseException:
        _cleanup(destination,created)
        raise


def main():
    parser=argparse.ArgumentParser(description="Offline database backup/recovery; never overwrite or resume")
    sub=parser.add_subparsers(dest="operation",required=True)
    for name in ("backup","restore"):
        cmd=sub.add_parser(name)
        cmd.add_argument("source")
        cmd.add_argument("destination")
        cmd.add_argument("--confirm-offline",action="store_true")
    cmd=sub.add_parser("verify")
    cmd.add_argument("source")
    args=parser.parse_args()
    if args.operation=="backup":
        result=create_backup(args.source,args.destination,confirmed=args.confirm_offline)
    elif args.operation=="restore":
        result=restore_backup(args.source,args.destination,confirmed=args.confirm_offline)
    else:
        result=verify_backup(args.source)
    print(_json(result))


if __name__=="__main__":
    main()
