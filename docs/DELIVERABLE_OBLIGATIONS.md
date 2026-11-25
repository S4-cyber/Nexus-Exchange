# Operator durable deliverable obligation ledger

H08/R08/E28/E31/E32/E38. Base PR #66, 7fb5cb27d0ab60393e3d4ea07434dcca4958badd;
both Python CI runs green (574 tests); Windows preview pending at preflight.
Parallel correspondence PR #60 untouched.

## Candidate

- Fixed owner-thread CSV register action re-produces exact saved-plan sample
  from explicit source and requirements, checks prior contract/report/artifact
  pins, fingerprints an explicitly selected actual artifact and verifies
  byte identity. Reinspect current plan before registration. No implicit
  registration on export; no claim that file match proves delivery or origin.
- Separate bounded local SQLite ledger, content-addressed obligation identity
  from canonical requirements, QA report and artifact hash/size. Idempotent
  registration, exact plan scope, history and bounded list (up to 100).
  No source or artifact contents, file paths, customer data, payment details
  or actual contract persisted. Max 10,000 obligations, 16 notes per obligation.
- Explicit local evidence note references for acceptance claim, revision
  request or rejection claim. Record only the file fingerprint and declared
  kind; no document interpretation or actual acceptance. Append-only
  sequence/hash chain, expected-head compare, nondecreasing time, unique
  reference, atomic writes/rollback, no overwrites/retries. Historical reads
  and evidence notes remain possible after profile/lead drift, without
  reinstating current eligibility or permission. The local owner decides
  which evidence to note; all verification, invoice, payment, revenue and
  execution flags remain false. No external actions.
- Eleven real local tests using actual prior saved scenario, preview and
  exported file: match/mismatch, idempotency, historical scope, evidence
  conflicts, integrity, halt, rollback, bounds and time. No live customer
  records, paid infrastructure or local test run claimed.
- Trust boundary: local database and filesystem are trusted, hashes are
  integrity checks not signatures or proof against an adversarial owner.
  Byte match does not authenticate customer identity, contract, payment,
  or evidence content. Cross-database rechecks are not distributed atomicity.
  No native ledger controls in this increment; callable backend only.
  Windows preview not required for this backend-only branch; prior build
  status must be checked separately.

Next: native registration and historical evidence controls, obligation-linked
mock invoice and partial/duplicate payment reconciliation. Independent
acceptance, authorized legal commitments and real money remain separate.
Formal main release acceptance 0/42 pending integration/review.

## Windows smoke regression repair

PR #66 Windows run 45560587599 passed 574 unit tests but failed native CSV
preview before packaging. Diagnosis: schedule_sha256 from the Council snapshot
includes evaluated_at, so real-time repeated inspection changed the contract
identity even when the saved plan and requirements were unchanged. Replaced
that time-dependent pin with a v2 immutable schedule-scope fingerprint derived
from the saved content-addressed plan ID, context and scenario fingerprint.
Fresh Council/source checks still run before publication and registration;
expiry and source/profile drift remain blocking. Draft v1 transient previews
must be regenerated; no production migration or previously accepted record
claimed. Three new advancing-clock/expiry tests; smoke preserves the original
error and closes the runtime before Windows temporary directory cleanup.
The new branch explicitly triggers full Windows source/frozen verification.
