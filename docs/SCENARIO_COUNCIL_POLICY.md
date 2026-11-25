# Scenario-bound local Council policy (review candidate)

E13/E14/E15/E22/E31/E38. Extend the verified guarded coordinator at 42a7e1dff7275094bdc9b916d040aca38702aae7 (351-test CI 45545857657) with a fixed local scenario policy. No external provider or agent-supplied verdict is admitted.

## Implementation plan

1. Resolve the exact saved plan from the trusted archive with current declared profile and UTC evaluation time. Use one read transaction for the saved plan, current lead and all bounded reference associations; no arbitrary file reads.
2. Derive one deterministic task scope from the immutable saved-plan ID and a fixed policy namespace. Pin the versioned policy and ordered criteria; canonical immutable plan input bytes are integrity pins, not independent evidence. Dynamic local checks may change at each attempt without changing the pins or task ID. Never accept caller-supplied criterion callbacks, pins, scopes, or statuses in the scenario-facing API.
3. Fixed checks: source/capability research suitability, modeled positive net and budget, delivery/preparation schedule, modeled wait until collection, and per-assumption reference coverage. Negative fit overrides unresolved inputs for that check. Missing model inputs/references are unresolved. Historical awards, stale/blocked sources, unsuitable classifications and unselected sources cannot pass the source check.
4. Inspect without reserving an attempt. Explicitly register before a single review. Invoke the guarded coordinator with the immutable plan-integrity artifacts for resolved criteria; omit unresolved criteria so the local evaluator returns missing material. Predicates capture deterministic current-snapshot checks, not source documents or arbitrary agent code. Reuse the same task across new reference associations. Third unsuccessful attempt escalates; no automatic replay or retries.
5. Display snapshot UTC, exact plan and context, check states, modeled metrics, reason codes, reference coverage and zero independent factual verification. Keep all authority flags false even with complete reference coverage. Only report digest and attempt metadata persist in the Council ledger; full evaluation snapshots are returned, not durably journaled.
6. Recheck halt and current profile revision around operations. Archive snapshot transaction and separate Council journal are not a distributed atomic transaction; if a profile changes after a ledger commit, the old-scope historical attempt may remain but no current result is returned. Explicit owner review and recovery remain necessary.
7. Test local-only fixtures, stable scope, negative/unknown economics, stale source, award rejection, profile/observation changes, restart/third-attempt terminal behavior, and privacy. No new desktop or packaged executable claimed.

## Reference audit
- Nexus Operative read-only nexus/council.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: deterministic specialist roles and veto separation; no trading code or credentials copied.
- Pinned agency-agents 8ae6164602c95ca78828b148b9052460ee426885, MIT license and strategy/coordination/handoff-templates.md reviewed for bounded criterion handoff and third-attempt escalation. No external prompts or code adopted as privileges. Exchange #2 and Operative #116 reviewed.
- Existing Python standard library and local stores only. No external services, no new dependencies or spending.

## Boundaries
The five checks are local research/model checks, not independent reviewer authentication or issuer/fact verification. The expected digests identify locally validated immutable plan inputs, not independently sourced commercial evidence. Reference coverage is only a count; files are not re-read or authenticated. A positive local review allows further nonprivileged review only. No authority to contact parties, submit bids, sign, pay or accept commitments. Main formal acceptance 0/42. Next: runtime-bound recovery and native Council review, independently sourced evidence and consolidated release review.

## Observed verification
- Test-first e437b8ff59cbd07ef913aaae43afc589f663697c, run 45546286953: expected missing-module error. Implementation fdff88969448a1bff84b854927c49c93a3fc0379: 363/363 tests on Python 3.10 and 3.13 (45546379087, jobs 138976888243 and 138976888573). Twelve new fixture tests.
- Expanded regression revision b72e0035781e86327a742ef0a0296749ae58df0b adds snapshot fingerprint stability, post-commit profile drift suppression and declared classification veto tests; exact-head verification tracked separately. Fifteen new tests total.
- Context7 CPython 3.13.14 sqlite3 explicit transaction control docs reviewed, compatible with Python 3.10; no additional dependency adopted. Prior verified Aegis desktop build 20d177090d35c5fabb969fa580012c164ac78cff (45543746266, artifact 14990835831) does not contain Council integration.
- Draft PR #46. No merge or formal gate acceptance. The review report digest is persisted in the ledger, while the full dynamic snapshot and its fingerprint are returned only. This is not a durable full-snapshot audit trail; adding one requires a versioned storage design and atomic binding to the ledger.
