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
RuntimeGuard now performs bounded batch reconciliation under its existing
exclusive directory lock and owner-thread idle/halt checks. Startup remains
halted; same-session outstanding reservations block resume until explicit
maintenance. The desktop has a separate recovery control. No worker exists
yet; future worker integration must prove process death and exclude active
supervisors before allowing this recovery. No running worker, timer,
network, model, replay, commercial authority or durable approval grant.

The store is intended for a trusted cooperating local directory. SHA-256
and schema checks detect accidental corruption or mismatch, not a malicious
local owner who can rewrite the database and digests. The 10,000-plan bound
and 8 KiB record cap are fail-closed; no deletion or rollover is implemented.
Closed-instance database backup now includes the optional ledger; restoration
retains reserved attempts, which the halted runtime reconciles without replay.
Backup remains unencrypted and subject to existing access controls.

## Verification

Seven focused SQLite tests pass locally using mocked advisory boundaries.
Three additional integration tests exercise the actual Council contract,
expired completion, escalation and closed backup/restore. Hosted checks
and independent review remain necessary. No new runtime dependency.


## Runtime-owned advisory recovery — 2026-11-25

- E15/E16/E17/E18/E19/E31/E37/E38/E40, H03/H06/H07: bounded all-plan advisory ledger reconciliation in one transaction, preserving completed states and consuming interrupted reservations; third interruption escalates. Corruption, future timestamps, capacity or a later write failure abort the batch. RuntimeGuard acquires its existing directory lock, starts halted, reconciles optional advisory ledger, reports counts, refuses resume while reservations remain, and requires halted owner-thread idle recovery. Missing ledger is not created. Desktop Settings exposes the separate recovery control and owned GUI smoke tests halt/recovery/resume using an actual saved Council snapshot; no model or dispatch.
- Three focused batch tests failed locally on the absent methods, then all ten isolated ledger tests passed in Python 3.13. Exact local ledger/test Git blob IDs matched. Five actual RuntimeGuard integration tests and native GUI smoke submitted for hosted verification. Full checkout DNS resolution failed; full local regression not performed. This is a cooperating local ownership boundary; future worker integration must prove process death and exclude its supervisor before recovery. Separate event, Council and advisory database recovery operations are not a distributed transaction. Independent review outstanding.
- Exact parent #106 eafabd9680b29b3dbb4bdd844c9eeef7239c5640: both Python 3.10 and 3.13 passed 853 tests (45676932177); Windows 45676932072 passed, artifact 15052078485. Separate UI PR #107 is based on RC3; preserve it and reconcile desktop edits during consolidation. No formal main acceptance (0/42), dependencies, model calls, provider calls, live commercial actions, paid resources or Operative changes.
- Next: fixed synthetic worker contract, actual child cleanup/timeout/death/halt, owner-thread supervision, exact scope revalidation independent of inspection timestamp, then approved runtime/model benchmarking.
