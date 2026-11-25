# Operator: deterministic column quality report

Base #80 472c6b7270117f1ff0bd94e301e3eb2fc390ef93; Python and complete Windows verification passed (45567112896).
The third service accepts an explicitly chosen UTF-8 CSV with exact declared
columns, unique nonempty key and 1–2000 rows, under the existing 256 KiB input,
16-column and 256-character cell limits. It fails closed on malformed data,
formula-shaped cells, duplicate keys or changed scope. It does not repair data.

Output is a canonical CSV, one row per input column, sorted by column name:
column, row_count, empty_count, whitespace_only_count, nonblank_count,
distinct_nonblank_count, min_chars, max_chars. Empty is exactly empty;
whitespace-only is nonempty but empty after stripping. Distinct nonblank
values are exact case-sensitive original strings, without normalization.
Lengths count Unicode code points, including empty values. No source cell
values are included in the generated report (column names and aggregate
statistics remain potentially sensitive). The verifier recomputes each metric
using a separate per-column calculation and checks canonical output bytes.

The explicit COLUMN_PROFILE operation has a separate immutable contract
format. Input schema remains pinned; QA describes actual output schema.
Legacy CSV and JSON preservation contracts and report digests remain unchanged.
Native preview/export/register and historical obligation records reuse existing
confirmation, input/hash/scope checks, and no-overwrite publication.
Scout narrow CSV quality/completeness/data-profiling title hints are advisory
only. Requirement matching expects preserve_all_fields=false for aggregate
output, not permission to change or delete source fields. No inferred facts,
buyer acceptance, payment or external action. No new dependencies.
