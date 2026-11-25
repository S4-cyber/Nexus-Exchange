# Scout exact receipt review

E06/E12/E18/E31/E33/E38; H03/H06. The native Review receipt control lists
the most recent 100 receipts and accepts an explicit numbered selection.
The exact task ID and displayed receipt digest are revalidated on a new
idle archive connection in a single read transaction; the historical
observation references are resolved without substituting newer records.
A same-source/key latest observation is displayed separately. Future
observations, older than 24 hours, and elapsed reported deadlines are
explicit holds. Cross-release/cross-provider supersession is not inferred;
the existing archive review still performs UK process-level checks.
No provider authenticity, current eligibility or execution authority is
established. Legacy and changed receipts fail closed. No network, writes to
records, new schema, automatic review, or commercial action.

Tests: exact historical digest, later/future same-identity observation,
age and future receipt, changed selection/missing evidence/halt, and empty
receipt. Full private checkout DNS unavailable; red/green not executed.
Coherent candidate code/tests/docs and existing hosted verification.

Predecessor #93 419264effb08be84c61238a486a5eeb808663e5e:
Python 3.10 and 3.13 each ran 801 tests and reported OK (45651419167);
Windows 45651419257 passed source, native GUI, fixture, Genesis, security
and frozen checks, artifact 15041705807. Independent release review and
formal main acceptance (0/42) remain outstanding.


## RC3 consolidation and exact receipt native acceptance — 2026-11-25

Predecessor #94 `ed5903a66bfaefa7627bcb04029f3d0bb55957cc`:
[Python CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45652000536)
passed 806 tests on both Python 3.10 and 3.13, including all five exact
receipt regression methods. Its [Windows CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45652000623)
passed source unit, source GUI, source fixture-process, source Genesis and
source security steps; packaging was in progress when this increment was
prepared. The earlier #93 Windows artifact 15041705807 is fully verified
for that revision only. The RC2 main-targeting draft #89 and stacked Scout
review branches remain available for independent review.

E06/E12/E18/E31/E33/E38/E39/E40, H03/H06/H07:
the owned desktop smoke now creates a receipt referencing the already
archived synthetic observation with the exact reviewed SAM query, checks
no duplicate observation is inserted, exercises the native historical
receipt review controller and rejects an out-of-range selection. The
nonblocking synthetic selector exists only in the smoke invocation;
normal UI uses the numbered owner dialog. Receipt/history controls occupy
a separate row. Source and frozen GUI smoke must pass for the consolidated
candidate. No provider calls, new dependencies, live authority or
financial commitments. Full local checkout failed with GitHub DNS
resolution; local red/green and independent QA not performed. No formal
main acceptance (0/42).


## Scout archive lifecycle continuity — 2026-11-25

E06/E12/E18/E31/E33/E38, H03/H06. Exact RC3 predecessor
13c7c1903eb76ad993022f64219ac755d3517a44 passed 819 tests on each Python
3.10 and 3.13 ([45670690819](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45670690819))
and full Windows source/frozen/GUI/Genesis/security verification
([45670690518](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45670690518),
artifact 15047864705).

Archive browse now maintains the maximum known UK release time and
distinct source/key identities at that time across all validated historical
observations, not just the latest retrieval for each identity. This avoids
losing an observed later release when a provider subsequently reports an
older release date for that identity, and avoids false ties from identical
re-observations. The local archive remains research-only; no cross-source
identity equivalence, compiled tender state, current eligibility or source
authenticity is asserted. Exact receipt review remains same-identity only.
The bounded archive cursor is streamed and closed even on failure; all
rows are validated before filtering, with the existing maximum-row gate
preserved. This reduces retained encoded payloads but is not a measured
performance claim. Three regression methods cover date regression,
distinct-event ambiguity, cap enforcement and corruption outside filters.

Reference: OCDS 1.1 branch pinned at
[1e98b792](https://github.com/open-contracting/standard/tree/1e98b792b2d48dfc806d974b08fccc1c50df5740),
Apache-2.0 LICENSE and schema/release-schema.json inspected: process ID,
release ID and publication date have distinct meanings. No upstream code
or schema copied, no packages installed; full dependency/maintenance audit
would be needed before adopting ocdskit. Rechecked agency-agents pinned
handoff template and Operative journal blob 59ee08e7734347897b29af33603dffba783ec9ad
for scoped evidence and bounded persistence; no Operative changes.
Full local checkout failed GitHub DNS resolution; local red/green and
independent review not performed. Superpowers unavailable. Atomic review
candidate requires exact hosted tests and Windows packaging. Formal main
acceptance remains 0/42. No new services, provider requests, expenditure,
or commercial execution.
