# Scout schedule feasibility (review-only)

R06/E14/E22/E35 candidate; extends the existing cash feasibility model. No dependency, provider traffic, UI, signature, submission, commitment or authority is introduced.

## Design and acceptance

- Use the existing archived lead projection, exact owner profile revision, and validated cash scenario. The calling code must resolve the lead from its trusted local archive; this function does not authenticate a caller-provided projection.
- Model **preparation** elapsed days from a supplied timezone-aware evaluation timestamp; modeled completion must be strictly before a precise reported submission cutoff. A date-only hint or missing cutoff is unresolved, never a positive fit. An award is not an open solicitation.
- Model **delivery** elapsed days separately, from an explicitly hypothetical contract start to an independently supplied hypothetical contractual due timestamp. Never substitute a tender cutoff for the delivery deadline. Reject chronology conflicts and past starts.
- Compare labor and preparation hours against declared average weekly availability using exact integer arithmetic. No calendar, concurrent workloads, working-day calendar, actual award timing or staffing is verified.
- UTC-normalize inputs and reject timestamps/elapsed periods outside the representable range. Unknown inputs propagate to affected outputs; an explicit negative fit takes precedence.
- SHA-256 binds the scenario, timing inputs, clock, reported source cutoff and source blockers; it is a fingerprint, not a signature or evidence authentication. Historical blockers are preserved. All independent verification, Genesis verification, execution and authority flags remain false, even when modeled timing fits.

## Test-first plan and evidence

1. Write tests for distinct timelines, cutoff equality, date-only/expired deadlines, unknowns, labor capacity, chronology, canonical digests, malformed data and Governor halt. Test-only commit 1ef7223fc379e473b01837fe09a79d850b7187c1; CI run 45537180101 Python 3.13 failed with the expected missing schedule module import (219 previous tests plus one import error).
2. Implement the pure model; implementation commit 54b718016e54107a3fceac99615f0f0d973da748.
3. Strengthen actual archive fixtures for CanadaBuys and USAspending and additional unresolved capacity/window tests; commit 9c4a41cbd46bf943124ad4cd0ef7c0b431223982. Twelve new test methods. Require exact-head CI and independent review before promotion. No formal main gate accepted.
4. Next: persist immutable scenario/plan inputs against trusted archive identity, show these explicitly hypothetical results in the desktop application, and integrate independent evidence checks; follow with restart-safe halt/recovery.

## Architecture sources

- Nexus Operative PR #116 and read-only nexus/risk_gate.py reviewed: preserve the default-deny concept, not trading-specific code. No changes to Operative.
- Open Contracting Data Standard pinned [eb57a46e69efead6ae62144fe1b7cefc53d07ff2](https://github.com/open-contracting/standard/tree/eb57a46e69efead6ae62144fe1b7cefc53d07ff2): reviewed schema/release-schema.json Period, Tender.tenderPeriod and Contract.period plus Apache-2.0 LICENSE and requirements.txt. The specification distinguishes submission and contract periods. Its docs build lists ocdskit and Sphinx tooling; do not install or port those dependencies. Full transitive security review and performance benchmarking are prerequisites to future dependency adoption, not performed for this conceptual review.
- Context7 retrieved Python datetime UTC conversion and elapsed-time documentation for CPython 3.13.14; used existing Python 3.10-compatible standard-library APIs. No third-party code copied or dependencies added.
- Agency-agents adaptation and draft PRs reviewed as untrusted design references; no changes to orchestration or authority.
