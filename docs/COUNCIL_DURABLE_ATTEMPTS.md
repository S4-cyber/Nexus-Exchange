# Durable Council attempt ledger (review candidate)

E15/E31/E38. Build independently on verified Aegis UI head 20d177090d35c5fabb969fa580012c164ac78cff. PR #43 criterion evaluator is a sibling in active review; head d0967bc3da977bc51bcccba4a76e199cf9670ad6 failed malformed Unicode digest test in run 45543915317. Do not modify or import that unverified branch.

## Acceptance plan

- Trusted in-process coordinator registers a normalized first-attempt AgentHandoff. Persist task ID and canonical digest of every immutable handoff field except attempt; no raw agent text, source text, artifacts or credentials. Same registration is idempotent, changed identity is rejected. Task IDs are trusted coordinator allocations, not arbitrary agent allocations.
- Reserve the exact next attempt atomically before invoking any review. Only one outstanding attempt per task. Attempts 1–3 never reset through registration, retries, concurrent connections or process restart. A reservation is a correlation identifier, not an authorization token.
- Trusted caller records only a canonical review status and SHA-256 report fingerprint; the ledger does not itself certify that the report was authentic or correct. Only ADVANCE_REVIEW_ONLY and ESCALATE are terminal; a third unsuccessful attempt necessarily escalates. Replay of the exact completion is idempotent; conflicting or stale completion is rejected.
- Explicit recovery under trusted exclusive ownership and after worker drain consumes an interrupted reservation without dispatch. Third interrupted attempt escalates. No background work or automatic retry/replay.
- Bound table and payload; canonical JSON/digest and transition validation; atomic BEGIN IMMEDIATE mutation; fail closed on malformed data, clock regression or halted/unknown state. All authority, facts-verified and release flags remain false.
- Test-first  e9578cfd7be98230de3a8c11c3ab9e2a251b286d; observe missing module and then both supported Python versions. Independent code review and integration with verified criterion evaluator remain separate.

## Reference and boundary audit
Read-only Nexus Operative nexus/risk_gate.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: exact boolean halt/unknown rejection; no trading code copied. Upstream agency-agents at 8ae6164602c95ca78828b148b9052460ee426885, MIT LICENSE (AgentLand Contributors 2025), strategy/coordination/handoff-templates.md inspected for standardized handoff and third-attempt escalation; concept only, no upstream prompts adopted as privileged instructions or code imported. Existing Exchange adaptation and draft Exchange #2 / Operative #116 reviewed. Context7 CPython 3.13.14 sqlite3 transaction reference reviewed for APIs compatible with 3.10. No new dependency, paid infrastructure, or external actions.

The trusted single-application storage and coordinator boundary is not authentication or a tamper-proof vault. No agent can allocate IDs, record verdicts, or declare exclusive ownership in the eventual integration. A hostile local database owner can rewrite both record and digest; operational integration must use RuntimeGuard and a trusted predicate registry. No GUI or Windows package changes in this increment. Formal main acceptance 0/42.
