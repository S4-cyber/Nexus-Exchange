# Durable local advisory attempts

The new advisory ledger is a standalone candidate for the future private
worker, not a live execution path. See [local advisory contract](LOCAL_ADVISORY_CONTRACT.md).

## Lifecycle and invariants

Reserve a current trusted Council snapshot under its stable saved plan ID,
after explicit consent and Governor permission. Each transaction chooses the
next attempt number, constructs the exact advisory request and commits an
immutable reservation before any future worker could be invoked. There is no
caller-controlled retry number, and refreshing a snapshot or changing a model
does not create a new budget for the same plan. Two cooperating connections
cannot reserve the same outstanding attempt.

Complete only with the same ticket, exact request, current trusted snapshot
and validated bounded response after the worker has drained. The persisted
review is digest-only. Reviewed is terminal and does not authorize execution.
Failure records retain only fixed reason codes; the third failure/interruption
escalates. Invalid completion leaves the reservation open for explicit
maintenance rather than silently retrying. A later reservation is impossible
until the previous one is closed; old tickets cannot complete a later one.

Halted recovery requires exclusive ownership and confirmed worker drain.
These flags are trusted caller assertions. The desktop RuntimeGuard does
not yet wire this store into startup, halt or worker dispatch, so the new
API must not be used as an independently authenticated security boundary.
There is no running worker, timer, network, model, automatic recovery,
commercial authority, or durable approval grant.

The store is intended for a trusted cooperating local directory. SHA-256
and schema checks detect accidental corruption or mismatch, not a malicious
local owner who can rewrite the database and digests. The 10,000-plan bound
and 8 KiB record cap are fail-closed; no deletion or rollover is implemented.
Closed-instance database backup now includes the optional ledger; restoration
retains reserved attempts, which must be reconciled explicitly, never replayed.
Backup remains unencrypted and subject to existing access controls.

## Verification

Seven focused SQLite tests pass locally using mocked advisory boundaries.
Three additional integration tests exercise the actual Council contract,
expired completion, escalation and closed backup/restore. Hosted checks
and independent review remain necessary. No new runtime dependency.
