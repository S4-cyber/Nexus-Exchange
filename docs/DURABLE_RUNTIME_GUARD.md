# Durable desktop runtime guard (review candidate)

E17/E31/E34/E38: every application session starts halted, including first launch, ordinary reopen and crash restart. Explicit Resume offline is necessary after validated recovery. No live action permission is introduced.

## Plan
1. Acquire a nonblocking exclusive OS file lock in the trusted local data directory for the lifetime of the application; release on close or process exit. Do not unlink the lock file.
2. Persist a versioned single-slot runtime state in the existing event journal. Validate existing state, monotonic revision and UTC timestamp. Record halted startup before recovery. Halt in memory first; if persistence fails, remain halted and refuse resume for this session.
3. Recover queued/running journal tasks as terminal interrupted events in one SQLite transaction, after validating journal ordering. No retry, external dispatch, or automatic success. Preserve existing terminal history. Recover all active tasks, not only one dashboard page. Refuse recovery on backward clock or malformed journal.
4. Resume only explicitly, with no active task or persistence fault; persist local-ready state before clearing the cooperative stop. The desktop retains the existing single worker, source-specific consent, and Governor external denials.
5. Connect GUI halt/resume, shutdown, result suppression and guarded export; verify source and frozen GUI smoke with synthetic temporary directory. Unit tests include actual second-process exclusion/crash, transaction rollback, recovery idempotency and failure injection.

## Boundaries
Cooperative cancellation cannot undo an already dispatched network GET or committed local archive write. The lock protects cooperating versions of the desktop using the same local filesystem directory; not older binaries, other processes editing the database, remote/network storage, or adversarial local filesystem owners. Startup does not trust a previously ready state. Local state is not authentication, an encrypted vault, or permission to transact. No auto-replay of interrupted work.

## Read-only reference audit
Nexus Operative risk_gate.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: halt/unknown-state veto, no trading logic copied. OCDS standard eb57a46e69efead6ae62144fe1b7cefc53d07ff2: release identity/date semantics, Apache-2.0 license and documentation dependencies inspected; no runtime dependency adopted. Context7 CPython 3.13.14 msvcrt.locking and fcntl.flock docs consulted, compatible with Python 3.10. Agency-agents adaptation and Exchange #2 / Operative #116 reviewed; no agent can resume or authorize work. No paid services or new dependencies.
