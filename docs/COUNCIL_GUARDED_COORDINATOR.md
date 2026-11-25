# Guarded Council integration candidate

E14/E15/E16/E31/E38. Work independently on verified ledger head 47e922769f5b6233a79235d50f2d5d929db96b82. The pinned sibling PR #43 head d0967bc3da977bc51bcccba4a76e199cf9670ad6 failed malformed Unicode digest validation (45543915317). Preserve its criterion tests and fix only the validation defect in this isolated candidate; no changes or merges to either sibling or main.

## Plan and safety boundaries

1. Retain all 14 pinned criterion-review tests. Validate exact lowercase 64-character ASCII hex before hmac.compare_digest. Re-run them in the candidate.
2. Add a trusted in-process coordinator which constructs a deterministic task ID from an exact stable scope SHA-256. Pin the trusted policy revision and ordered criterion names/artifact digests in the immutable handoff contract. Same scope with changed policy/pins/order conflicts; no automatic ID allocation from agent data. Local trusted code supplies predicates and stable scope/policy pins, not arbitrary remote messages.
3. Explicitly register tasks, validate complete bounded artifact mapping before reserving, then reserve the next attempt in the durable ledger before invoking any predicate. Call the corrected criterion evaluator directly; no supplied verdict input. Validate report identity and false authority flags, persist canonical report digest and status. Return a review-only result after commit and a final halt check.
4. One call runs at most one attempt. Missing evidence is a legitimate consumed attempt; malformed input is rejected before reservation. Halts, errors or completion failure after reservation leave it outstanding until a trusted owner explicitly recovers after worker drain. Never automatically retry or replay. No release or commercial action authorization.
5. Test restart, scope/pin conflicts, duplicate dispatch, malformed input, halt during predicate, reserve-before-check, completion failure, bogus report and negative predicate. Run both Python versions; independent review and operational integration remain separate.

## Reference audit

- Nexus Operative read-only nexus/council.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: deterministic specialist checks, veto separation and no broker authority; no trading code or credentials copied.
- Pinned agency-agents 8ae6164602c95ca78828b148b9052460ee426885: MIT LICENSE and strategy/coordination/handoff-templates.md inspected for criterion handoffs and bounded escalation; no prompt adopted as privileged instruction or dependency. Existing adaptation and PRs Exchange #2 / Operative #116 inspected.
- Context7 CPython 3.13.14 hmac.compare_digest and canonical JSON docs consulted; ASCII hex validated before comparison, compatible with 3.10. No new dependency.

Trusted scope allocation and policy digest/check registry are not authentication; callbacks are trusted bounded side-effect-free local code, not sandboxed or preemptively timed out. The coordinator does not independently establish commercial facts, authenticate reviewers, or integrate RuntimeGuard ownership/recovery or desktop execution. No autonomous dispatch, live transactions, spending, paid infrastructure, release or merge. Main formal acceptance remains 0/42.

## Observed verification
- Verified ledger baseline: 47e922769f5b6233a79235d50f2d5d929db96b82, 325 tests on Python 3.13 log and both unit jobs green (45544307449). Prior Aegis desktop preview is not the integration candidate: verified head 20d177090d35c5fabb969fa580012c164ac78cff, Windows run 45543746266, artifact 14990835831.
- Test-first c0b0087888056775f2ad74805e56b950a95164c4, run 45545595227: expected missing criterion module. Narrow correction 244fef4c68e700526c5bbca58c971252aef021c0; formerly failing malformed-digest test observed passing in 45545658627; overall run was not green until coordinator existed.
- Integrated coordinator cae6f9e76bdc2aa59ec6ef49136bc46d6290dbb1, run 45545685803: 349/349 tests passed on Python 3.10 and 3.13 (jobs 138974614305 and 138974613978). All fourteen pinned sibling criterion tests and ten new coordinator tests included.
- Additional report-boundary tests 068ca31a10b862dede5fc096d8566d81ddf6ba8d, run 45545737240: two expected failures (wrong artifact snapshot and extra fields accepted). Fix af34de4ecc2cb08fba2ff4fb322029033b5f57a4 requires exact report schema and recomputes actual snapshot digests before persisting result. Exact code-head verification pending at entry.
- Draft PR #45. The original PR #43 head remained unchanged at d0967bc3da977bc51bcccba4a76e199cf9670ad6 when checked; its failed CI is not overwritten or represented as passing. No main merge or new Windows build.
