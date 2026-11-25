# Durable Council review audit (review candidate)

E18/E19/E31/E34/E38. Built on the verified scenario policy head 50efa4628127952d851749d705202d7f9b4974aa (366-test CI 45546491474).

## Design
- Keep the attempt ledger and bounded audit records in the same local council.sqlite3 transaction. A v2 ledger entry links to the exact audit SHA-256; a separate table holds the historical snapshot and criterion report. Attempt completion and audit insertion commit together or both roll back. A reserved attempt remains consumed after failure; no automatic replay.
- Persist only canonical structured metadata: saved plan and observation/profile fingerprints, evaluated UTC, policy/criteria and model results, reason codes, bounded evidence-reference IDs, cash/schedule model digests, reservation/contract identity and review report. No document bytes, filenames, paths, credentials or free-form agent messages.
- Validate snapshot identity, canonical context, fixed criterion order, reference coverage, amount/time bounds, report identity, ordered artifact pins, exact handoff/contract digest and false authority flags. Store a digest of the canonical audit and cross-check it with the ledger on every task read. Detect missing, corrupted or orphaned linked audits. Exact replay is idempotent; changed replay and downgrade from audited completion are rejected.
- Version 1 digest-only records remain readable; migrate a task to version 2 upon its first audited completion. Existing attempts remain honestly labeled LEGACY_DIGEST_ONLY; incomplete reservations and interrupted attempts have no fabricated audit. Older code that does not support v2 is not compatible with those records.
- Historical retrieval is halted-state gated, does not depend on today's profile or live opportunity status and never establishes a current decision. This is a local integrity check, not a signature or independently verified source/issuer. A local adversary capable of rewriting the entire database and all hashes is outside the trust boundary.
- ScenarioCouncil uses the new audit path; generic trusted coordinator callers remain backward-compatible with digest-only completion for v1 tasks. No new Windows build, UI, independent reviewer authentication, operational recovery binding, network requests, live transactions or paid infrastructure.

## Verification plan
- Test-first 8890fd7d19dce803254f36bb48b057b87ce6ca74; run 45546866700 observed expected missing audit module.
- Audit schema 2251dece5bbf66f6222eb29a4f3cb4a5a1bd52cf; ledger atomic association 9b5ce37ea65eaf6d5032276ac3f19c30ad5038aa; coordinator ff0b34deb01f44ac1cb95698c185152bc599284f; scenario adapter 7522eb2129bdadb5e5e053fc3586c9500d2ca5b0. Exact combined CI tracked separately.

## Reference audit
- Nexus Operative read-only nexus/journal.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: bounded canonical local journal and atomic transactions, no raw trading datasets or credentials. No trading code copied.
- agency-agents MIT at 8ae6164602c95ca78828b148b9052460ee426885: reviewed LICENSE and strategy/coordination/handoff-templates.md for acceptance criteria and escalation provenance; no new code dependency or privileged prompts adopted. Existing adaptation and Exchange #2 / Operative #116 reviewed.
- Context7 CPython 3.13.14 SQLite transaction documentation consulted; use explicit BEGIN/COMMIT/ROLLBACK and Python 3.10-compatible APIs.
- Main acceptance remains 0/42. Next: trusted runtime recovery, native Council historical review dashboard, stress/security and consolidated release review.
