# Operator: exact two-file CSV reconciliation

Base #81 3dcf338b418126961cd91988e735c12e87ef9f9c: 694 tests and complete Windows source/frozen smoke passed
(45567746249). The fourth service compares two owner-selected UTF-8 CSV files
with identical declared column sets, exact nonempty unique keys, and independent
declared counts. Each file is bounded to 256 KiB, combined rows to 2000,
columns to 16, and cells to 256 characters. No fuzzy matching, normalization,
deduplication, formula execution, missing value inference, editing or merging.

Output is a canonical CSV, one row per union key sorted by key. Columns are
record_key, status (LEFT_ONLY, RIGHT_ONLY, CHANGED, UNCHANGED),
changed_field_count and changed_<input-column> for each non-key column in
declared order. Matched records have YES/NO flags, unmatched records have
NOT_COMPARED and count 0 (not evidence of equality). No non-key values are
copied into the report. Keys, column names and status remain potentially
sensitive and require review before any external use. Output remains bounded
to 512 KiB; oversized reports fail closed.

The separate immutable reconciliation contract pins both source hashes and row
counts, shared schema, selected plan and scope. A distinct report format binds
both input byte counts and hashes and actual output identity. QA independently
recomputes key union, exact statuses and changed flags, and checks canonical
serialization. Historical ledger reconstructs allowed output schema and
union-count bounds without claiming to re-read historical source bytes.
Legacy contract and report formats remain unchanged. Native preview/export
and explicit registration re-read both files and require matching pins.
Scout recognizes narrow CSV reconciliation/comparison title hints; declared
requirements require both source sizes and exact specification, not verified
availability or authority. No external delivery, real acceptance or revenue.
