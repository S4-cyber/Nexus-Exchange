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

## Scout report compatibility and downgrade precautions (review candidate)

The database-only backup does not include engagement-latest.json, even though
new Scout terminal journal events may carry a SHA-256 digest of its report.
Preserve this file separately with the closed instance, along with user evidence
and artifacts; do not advertise the database backup alone as a complete Scout
history snapshot. The latest report can be absent or unconfirmed after an
interrupted publication. Do not synthesize a digest, terminal success or report
from incomplete records. A readable legacy JSON report may exceed the archive
limit after canonical encoding; preserve the original bytes for review rather
than repeatedly retrying or manually truncating it.

Before an upgrade, halt, close and drain the application, verify the existing
backup using the documented source CLI, preserve non-database files in a
separate protected location while the instance remains closed, and record the
exact application build identity. Use a distinct new test directory for any
restore; keep original data and backup untouched. This manual procedure is not
a transactionally verified combined snapshot and has not completed a downgrade
drill. Older builds may reject digest-bearing journal records or newer schemas.
Do not point an older build at upgraded data, strip event fields, edit the journal,
or resume automatically. Only use a verified pre-upgrade backup with its matching
build for rollback; otherwise retain the data and use the compatible newer reader
until a reviewed migration exists. All acceptance and legal/authority safeguards
remain in force. No user data is uploaded or shared.

## Optional combined snapshot v2 (candidate)

Pass `--build-id <exact-lowercase-40-character-git-commit>` to the backup command to opt in to a combined closed-instance snapshot. This is an operator-asserted build identity, not a verified executable signature or downgrade guarantee. The manifest explicitly records whether the latest Scout report exists; when present it is copied byte-for-byte, bounded to 1 MiB, validated by the existing strict report decoder, hashed, and rechecked under the same runtime lock as the databases. Restore verifies actual destination hashes, preserves raw legacy encodings, and never resumes automatically. Invalid reports fail closed without replacing original data. Preserve malformed files separately for review. Existing v1 database-only manifests and commands remain readable and unchanged; v1 does not include the report. User evidence and exports remain excluded. A report digest is local integrity evidence, not source authenticity, verified successful task completion or permission. No directory-level power-loss or adversarial filesystem guarantee. Test a separate restore with the matching build before relying on it. Full native recovery drill and independent review remain outstanding.

## Combined snapshot journal semantics (review candidate)

V2 now also runs the existing bounded event projection on the copied events database during creation, verification and restore. SQLite quick_check and matching file hashes alone cannot detect invalid task-state transitions. Valid interrupted or unconfirmed tasks remain intact; no digest is synthesized, no automatic replay or resume. This does not authenticate history, establish report-to-journal agreement, or validate every other database's application schema. V1 behavior is unchanged. New tests cover invalid transitions in the original and rehashed backup, plus abrupt process exit followed by halted recovery and separate restore. They are written but not locally executed; direct checkout DNS failed. Native recovery and independent acceptance remain outstanding.
