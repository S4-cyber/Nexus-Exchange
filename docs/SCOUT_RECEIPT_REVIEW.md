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
