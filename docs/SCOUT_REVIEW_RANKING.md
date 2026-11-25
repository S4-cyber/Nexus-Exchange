# Scout bounded review ranking (review candidate)

R06/E13/E14/E22/E33/E35/E38: deterministic research ordering for exact archived observations and hypothetical saved plans. The ranking is not a calibrated profit forecast, independent evidence verification, commercial qualification, or approval to act.

## Scope and ordering

- `RankingStore(path)` extends the existing single-user ScenarioStore and uses one SQLite read transaction for history, latest observations and saved plans. The caller supplies the current declared profile, aware clock and trusted halt state; no new credentials or permissions.
- `rank_review(profile=..., now=..., source=None, query="", limit=25, scan_limit=100, halted=False)` first selects a bounded window from the existing profile/history ordering. The returned report records matched/evaluated/returned counts and scan/output truncation. It never claims a global optimum or rank outside the scanned window.
- Use the latest saved immutable scenario in the exact observation/profile scope; no optimistic search over alternative assumptions. Equal newest timestamps are ambiguous; future-dated plans are unresolved. Superseded observation/profile plans are excluded.
- Source lifecycle, collection completeness, source selection and declared capability mismatch take precedence over financial fit. Historical contractor awards are intelligence only, not open opportunities. Source-provided classifications are kept separate from owner declarations; neither constitutes independent verification.
- Tiers: MODEL_FITS_UNVERIFIED, MODEL_UNRESOLVED, MODEL_DOES_NOT_FIT, SOURCE_REVIEW_REQUIRED, CONTRACTOR_INTELLIGENCE_ONLY, SOURCE_NOT_SELECTED. Explicit negative budget/schedule/net fit outranks unknowns as a negative verdict, not as a preferred opportunity.
- Within the first tier, order by existing declared profile priority, lower modeled pre-payment exposure, shorter modeled wait until collection (including elapsed wait to contract start), then greater modeled expected net. Use exact Decimal and integer microsecond comparisons. Other tiers use existing profile priority and stable archive order, not missing amounts treated as zero.
- No actual compensation, source freshness, owner capability, actual cash balance, delivery, collection, evidence or authority is verified by this ranking. All authority flags remain false. Owner checklist assertions are deliberately not counted as independently verified evidence.

## Verification plan

1. Test-first revision 99493e45f1037689135b1ddcb7536bdd0b4ebce7; run 45540775218 Python 3.13 observed expected missing-module import error.
2. Implement review ranking 785c01e44bccc8687893773c74405acc8e0ba8f7; extend regression tests 51330e1207a9d19cea9812b6a9d5664842a83034. Fifteen new methods cover missing/negative inputs, stale/superseded records, latest-plan ambiguity, future records, source controls, exact economic order, Genesis, delayed start, corruption, bounded scans and halt.
3. Require exact-head CI and independent review. Desktop ranking view, per-assumption evidence, performance/stress checks, durable halt, interrupted-task recovery and release consolidation remain pending. No new executable is claimed for this backend increment.

## Reference audit

- Nexus Operative read-only `nexus/council.py` at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: deterministic specialist veto and reason-code architecture reviewed; no trading logic or code copied.
- OCDS standard at eb57a46e69efead6ae62144fe1b7cefc53d07ff2: reviewed Classification and Period definitions, Apache-2.0 LICENSE and docs requirements. Retain scheme-specific classifications and explicit unknown time bounds. Documentation tooling (ocdskit, Sphinx) not installed; transitive dependency/security and performance review required before any dependency adoption.
- Context7 Python CPython 3.13.14 docs consulted for Decimal.copy_negate and stable sorting, compatible with existing Python 3.10. No new external dependency.
- Agency-agents adaptation and draft PRs Exchange #2 / Operative #116 reviewed; no agent assertion can override source holds or Governor policy. No external authority introduced.

Single-user offline storage only; no authentication or encrypted vault. Source content and model inputs are unverified. No additional service expenditure, no live operations, no formal main gate accepted.
