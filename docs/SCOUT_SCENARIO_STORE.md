# Persistent Scout scenario store (review-only)

R06/E18/E22/E31/E35/E38 candidate. The desktop can eventually save and reopen hypothetical financial and scheduling inputs without relying on prior assessment results. No UI, live actions, network or new dependencies in this increment.

## Interfaces and invariants

- `ScenarioStore(path)` extends the existing single-user `LeadStore` on the **same SQLite file**; additive versioned table `scout_scenarios_v1` and scope index. Existing lead archive remains readable using `LeadStore`. The caller is responsible for local filesystem access controls, trusted clock/halt and the current declared profile.
- `save(context, scenario, plan, profile=..., now=..., halted=False)` validates the exact historical observation/profile revision against a fresh archive lookup within the same BEGIN IMMEDIATE transaction. It validates both modeled timing and financial inputs using the existing validators, canonical USD decimals and UTC timestamps. Unknowns remain null; no raw source response, profile payload, personal data, free-form text or credentials are stored in the new table.
- Immutable content-addressed plan ID excludes creation time, so exact semantic replay preserves the original record. Changed terms or context create a distinct ID. Capacity 10,000 plans, 8,192-character canonical payload, no automatic pruning.
- `get(plan_id, halted=False)` returns historical inputs only. `list(context, limit=100, halted=False)` is exact-context scoped, bounded and deterministic. Records validate the canonical payload, digest, identity, scope and creation timestamp. Hashes detect ordinary corruption/identity mismatch, **not** deliberate authenticated tampering by someone who can rewrite the database and all identifiers.
- `evaluate(plan_id, profile=..., now=..., halted=False)` performs a consistent read transaction, rejects backwards evaluation time and resolves the latest archive observation with the supplied profile. A changed or missing observation/profile prevents reassessment until the caller explicitly saves a new plan. Dynamic freshness and deadline blockers are recomputed; past model verdicts are never persisted.
- All methods deny unknown or asserted halt states. A positive modeled fit is not independently verified feasibility, funds, execution eligibility, licensing or authority. No new external permissions or agent verdicts.

## Test-first plan and evidence

1. Add persistence/reopen, immutable replay, exact context, recalculation, stale deadline, halt, schema, tamper and capacity tests. Test-only commit acfbc6c726a0311cbfc4b5c6affc03882b4cb67a; CI 45538333181 Python 3.13 observed expected missing-module import error.
2. Implement local store. Commit e6cd0e2712c9645cbaaeb892c3a2db01ac4b8e6c. Python 3.13 CI job 138950626099 in run 45538409299 observed 243 tests passed.
3. Add cross-connection replay, scope isolation, injected SQLite INSERT failure and recomputed-payload identity regression tests; commit 40690c774567859027ab01f0b3510e6b4bb0a151. Fifteen new test methods total; require exact-head CI and independent review before promotion.
4. Next: native desktop scenario editor and historical plan list, explicit independently verified evidence per assumption, guarded review ranking, restart-safe halt and recovery. Source/profile revisions are not authenticated facts. No gate formally accepted on main.

## Reuse and dependency review

- Nexus Operative read-only `nexus/journal.py` at [6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11](https://github.com/S4-cyber/Nexus-Operative/tree/6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11): bounded journal, explicit transactions and no credentials. Adopt these architectural invariants using existing Exchange code; do not copy trading data, paths or code.
- Pinned OCDS [eb57a46e69efead6ae62144fe1b7cefc53d07ff2](https://github.com/open-contracting/standard/tree/eb57a46e69efead6ae62144fe1b7cefc53d07ff2): inspected schema release identifier, date and contracting process identity definitions, Apache-2.0 license and docs requirements. Maintain version-specific observations rather than conflating releases with processes. No upstream code imported; documentation dependencies (ocdskit, Sphinx etc.) not installed. Full dependency security and performance review is required before actual adoption.
- Context7 CPython 3.13.14 SQLite transaction-control documentation: explicit BEGIN/COMMIT/ROLLBACK with isolation_level=None; APIs supported on Python 3.10. Existing standard-library runtime retained.
- Reviewed agency-agents adaptation and Exchange #2 / Operative #116. No agent-issued approval or execution path introduced.

This store inherits bounded archive lookup (up to 10,000 observations) and is not a multi-tenant or encrypted vault. Performance stress, retention controls, independent source verification, UI integration, Windows packaging and formal release review remain pending.
