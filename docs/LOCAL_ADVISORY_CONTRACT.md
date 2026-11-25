# Local advisory contract — implementation candidate

The standard-library module nexus_exchange/local_advisory.py implements a
closed data contract for a future local model. This is not an inference
engine, model installer, sandbox, or live agent runtime.

A trusted caller explicitly approves local advisory construction and
provides the current validated Council snapshot and a selected model
digest. The module invokes the existing Governor's local research policy,
builds the exact evidence context packet, and projects only fixed assumption
field identifiers, known states and bounded reference digests. The request
contains the source hold and exact snapshot/packet pins. It does not include
the raw source material, arbitrary instructions, financial amounts or
credentials. A requested model digest is not proof of the actual loaded
weights.

Requests are bounded to 64 KiB, responses to 16 KiB; the snapshot and
request must both be no more than five minutes old. The caller-supplied
attempt number must be 1–3; this is a schema limit, not a durable retry
enforcement mechanism. The response contains only format, request digest,
model digest and an ordered list of field/reason/reference ID items.
Unknown fields, conflicting states, duplicate items or JSON members,
fabricated or cross-field references, authority flags and commands are
rejected. The validator reconstructs the exact request from the current
trusted snapshot. A review output preserves all unresolved fields and the
source hold, regardless of omitted suggestions, and sets all authority
and independent-verification flags false.

This first stage is deliberately not wired to model calls, a GUI, network
transport, or automated task execution. Hashes are local consistency and
association checks, not signatures. Freshness depends on a trusted clock
and a genuinely current snapshot supplied by the caller. Model authenticity,
IPC isolation, hard deadlines, process termination, durable reservation/
retry accounting, model licensing, hardware benchmarks and independent QA
remain necessary. No model may override the deterministic Council,
Governor, explicit source consent or commercial approval.

Tests: five isolated response-parser tests and four hosted integration
methods exercising actual Council projection, stale context, hold,
consent, halt, attempt cap and resealed mutation. Prior upstream references
remain those pinned in resources/awesome/catalog.json and
docs/AGENT_ENGINEERING_ADOPTION.md. No upstream source copied, package
installed, network endpoint called or cost incurred.


## Durable local advisory attempt ledger — 2026-11-25

- E15/E16/E18/E19/E31/E37/E38/E40; H03/H06/H07. New standalone AdvisoryAttemptStore uses transactional SQLite reservations, canonical bounded digest-checked records and a maximum three attempts per validated plan ID across model or snapshot changes. A successfully validated response terminates that plan's advisory budget; the third failed or interrupted attempt escalates. No reservation replay, automatic retry, reset, model execution or action authority.
- Explicit Governor consent for reserve/complete/fail; exact current request and snapshot validation on completion; caller must confirm worker drain, and halted recovery requires exclusive ownership and drained workers. These are trusted coordinator assertions, not OS-level proof. The desktop RuntimeGuard does not yet wire this ledger into startup or dispatch. No automatic replay after backup/restore. The closed-instance database backup allowlist now includes local-advisory.sqlite3; only digests, fixed failure codes and timestamps are stored, never raw model output or credentials.
- Seven isolated Python 3.13 SQLite tests passed after expected missing-module failure, using actual storage/transactions, the Exchange Governor policy and mocked advisory request/response boundary. Exact local code/test blob hashes verified. Three real Council/backup integration methods added; full repository checkout DNS blocked, so hosted CI remains required. No independent review claimed.
- Parent PR #105 at 5d929b1d2c718c5340179702cd0b36070e18e36e passed both Python jobs (843 tests each; 45676020671). Windows 45676020523 still running at preflight. Preserve parent build; isolated review branch. Prior #104 Windows 45675295364 passed. No paid services, new dependencies, provider/model calls, commercial actions or changes to Operative. Formal main acceptance 0/42.
- Next: RuntimeGuard owner-thread facade, actual drain/recovery ownership, synthetic isolated worker timeout/process-death checks and bounded IPC; then separately verified local inference benchmark and dependency/license review.


## Owned advisory process fixture — 2026-11-25

- E15/E16/E17/E27/E37/E38/E40, H01/H06/H07: a fixed deterministic spawned Python child accepts an exact synthetic advisory request, returns bounded bytes in shared memory, exits before parent validation and is joined/terminated/killed as required. Deadline, unknown halt, nonzero exit, empty/oversized/forged output all fail closed. Explicit consent and existing Council request reconstruction apply at the public fixture boundary; no public target/command/model choice, no raw response returned by public wrapper. This is process separation and cooperative cleanup, not OS containment. The fixture is not a real model and does not consume a durable plan attempt.
- Six focused tests run locally against real spawned children on Python 3.13.5, including teardown checks for leaked children; exact local source/test Git blob IDs verified. Three actual Council integration tests plus owned source/frozen GUI smoke submitted for hosted CI. Full local clone fails DNS; no full local regression or independent QA claimed. Parent #108 exact 5dcf6450aaa7d3c93dfe4e46839e5d2daeb5848b passed 861 tests on Python 3.10/3.13 (45680763014); Windows 45680762786 active at preflight. Preserve separate UI PR #107 and ongoing build.
- No new packages, model calls, provider calls, paid services, actual commercial actions, or Operative changes. Formal main acceptance 0/42. Next: integrate the supervised synthetic worker with owner-thread runtime lifecycle and durable attempt reservations, re-inspect stable current scope independently of timestamp, then benchmark a separately approved locally licensed model under real containment. No automatic retries, cloud fallback, or tool authority.
