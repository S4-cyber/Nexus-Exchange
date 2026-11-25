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
