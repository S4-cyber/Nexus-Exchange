# Offline database backup and recovery (E18/E19/E31/E37/E40)

Base RC1 #74 5bbdc4a891cfaa56ff8efa887ad447ec49343508: both push/PR
Python jobs green (654 tests); Windows source smoke passed, packaged
verification pending at preflight. Prior #73 full Windows passed.

## Closed local database maintenance only

Acknowledge explicit offline confirmation. Existing trusted absolute local
source directory, existing runtime lock, clean shutdown row; acquire lock
while all cooperating processes are excluded. Known ten database filenames
only; required events/runtime tables, minimum expected tables per database,
SQLite quick_check(1) and exact halted/shutdown state. Deny unknown database
names, sidecars, symlinks at files, oversized files. 128 MiB/file, 512 MiB
total. Read-only immutable SQLite inspection is only appropriate for these
closed copies. Unknown non-database files are excluded; no claim of a complete
user-directory backup. No source modification beyond opening the existing
lock file, no migration, credentials, network, paid service or new dependency.

Create a distinct new directory with exclusive mkdir and exclusive file
creation. Copy/hash bounded bytes with stable file identity, fsync each file,
rehash originals before releasing runtime lock, write canonical manifest last.
Verify exact inventory, digests, SQLite consistency, schema and runtime state.
Restore only to a distinct new directory, recheck exact backup before/after,
no overwrite or auto-resume. Failed operations attempt cleanup of owned
new files only. The runtime creates a new lock and starts halted. No directory
fsync/power-loss atomicity guarantee. No in-place recovery, malicious
filesystem/ancestor defense, network share detection or cryptographic
authenticity. Backups are NOT encrypted. Use trusted local access-controlled
encrypted storage; do not send database copies to GitHub or third parties.
Original evidence and exported artifact files are not copied; retain separately.
A corrupted/tampered database may still pass quick_check if internally valid;
semantic store validation remains required after startup.

## Commands

Use absolute paths and a closed instance:
- python -m nexus_exchange.database_backup backup <source> <new-backup> --confirm-offline
- python -m nexus_exchange.database_backup verify <backup>
- python -m nexus_exchange.database_backup restore <backup> <new-test-data> --confirm-offline

Source-only maintenance CLI; no GUI or packaged maintenance command yet.
Never restore over a live data directory. The diagnostic now backs up the
owned synthetic instance after partial settlement, restores to a separate
new directory and opens that restored copy, requiring explicit resume,
then validates historical Council audit, obligation and receipt chain before
final modeled settlement and reserve calculation. No real user files touched.
The preview bundle verifier requires this diagnostic stage.

Nine new regression methods for real local database copying, halt/lock,
confirmation, destination, sidecar, corruption, schema/state and cleanup.
Existing deterministic Genesis test exercises full copied recovery. CI source
and frozen Genesis smoke require the same recovery path. No local test run
claimed. Main gate acceptance unchanged 0/42. Next: dependency/license and
independent security review, native maintenance usability, verified RC build.
