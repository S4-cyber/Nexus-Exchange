# Operator native CSV work sample (H08/R08/E27/E28/E32/E38/E40)

Base PR #65, exact head dbaa45329bf1f09d80ddc0040c35027b81e9324c:
both Python push/PR CI passed (563 tests); prior Windows preview #64 passed.

Adds native saved-plan workspace reachable from Scout scenario planning and
Ranked Matrix. Explicit selection of an absolute local .csv, declared output
columns, unique key and exact row count, then preview. Display up to ten data
rows and QA fingerprints. Opening does not read or write a file. Requirement
edits or busy/halt invalidate the transient preview; export consumes it.
No source filename or path in output report or persistent data.

Owner-thread RuntimeGuard admits only fixed preview/export operations, verifies
source scope and declared schema before touching input, performs bounded
stable regular-file read with identity/timestamp checks, uses previous
deterministic production and independent local reparse QA. Export reruns the
entire process against the current plan and source, checks exact contract,
report and artifact fingerprints, then writes a same-directory temporary file
and fsyncs before an atomic hard-link publication to an unused .csv name.
No overwrite, fallback or partial destination on pre-publication failure.
Existing destination including input and dangling link is rejected. Temp
cleanup is attempted on all paths. Windows NTFS/local filesystem hard links
required; unsupported filesystems fail closed. A halt or failure after the
publication point can leave a complete output file; inspect destination.
No directory fsync/power-loss durability guarantee; trusted local filesystem,
not protection against adversarial path changes, mapped network drives or
malicious processes. No arbitrary directories created, no file content
executed, no network, credentials, dispatch, paid resource or customer data
uploaded.

Eleven real local tests for file selection, exact preview/export, source/profile
drift, halt, existing and racing destination, cleanup and unsupported link
behavior. Source/frozen Windows GUI smoke exercises native preview/export
using owned synthetic fixture only. No local test execution claimed;
exact-head hosted CI required. Formal main acceptance remains 0/42.
Next: durable obligation/acceptance ledger linked to exact artifacts, then
mock invoice and collection reconciliation. Customer acceptance, awards,
financial eligibility and actual revenue remain false.
