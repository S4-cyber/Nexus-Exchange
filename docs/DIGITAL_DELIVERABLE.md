# Operator digital deliverable — deterministic CSV work sample

H08 / R08 / E24 / E27 / E28 / E32 / E38 (candidate, not gate acceptance).
Base PR #64, 139a83c3181228e7cf550a59be0af1bf0248f44e. Both push and PR
unit CI and Windows preview passed. Separate correspondence PR #60 preserved.

## Concrete local work capability

Standardize an explicitly supplied UTF-8 CSV to a declared column order and
ascending unique-key order, with exact field preservation. Output is real
CSV bytes, not a simulated claim that an artifact exists. The owner declares
the source byte fingerprint, output column order, unique key and exact row
count. The local contract pins the current saved plan, observation, profile,
financial assumptions and delivery schedule. Source-held/stale/superseded
scenarios cannot generate a scoped sample through RuntimeGuard.

Fixed input cap 256 KiB, output cap 512 KiB, 1–2,000 rows, 1–16 columns,
256 characters per cell, strict ASCII header identifiers, exact row width,
nonempty distinct keys. No data interpretation, code, formulas, paths, macros,
network or external API. Reject rather than rewrite malformed, control-bearing
or formula-shaped cells (including leading whitespace and compatibility forms;
negative text numbers are conservatively rejected). Quote every output field,
CRLF line endings, UTF-8. No row dropping, inferred fields or silent deduplication.

The QA pass reparses both source and output, compares the exact keyed records,
checks the source fingerprint, schema, expected row count, uniqueness, cell
policy, ordering and canonical bytes. The separate report carries source,
artifact, contract and report fingerprints, byte/row counts and check names.
These are deterministic local integrity checks, NOT independently authenticated
evidence, customer acceptance, actual compensation or proof of zero cost.
No buyer acceptance, contract award, invoice eligibility, external execution
or revenue flag can be granted.

Owner-thread RuntimeGuard operation uses the existing exclusive/idle/healthy/
halt checks and fixed local confirmation, blocks outstanding Council reservations,
reserves Operator activity, checks halt during every row and re-resolves current
scope before returning. No arbitrary callback or shell action. Bytes and report
are transient; no file read/write, credentials or paid resources. No desktop
button or export yet; this is a callable candidate, not a user-facing production
delivery workflow. Cross-database scope checks use existing trusted local model;
not adversarial authentication or distributed atomicity.

Ten regression methods on actual archived scenario and RuntimeGuard, exact
artifact bytes, tampering, formula/duplicate/width failures, bounds, halt,
owner-thread, profile drift, stale/superseded source and reentry. One coherent
commit; no local test execution claimed; hosted exact-head verification required.

## Next

Native explicitly selected local file workflow with bounded stable file read,
preview and non-overwriting export; preserve exact contract/artifact/QA identities
and independent acceptance in an obligation ledger; simulated invoice and
collection reconciliation. No delivery, submission, contract or real payment
automation. Formal main release acceptance remains 0/42 pending consolidation.
