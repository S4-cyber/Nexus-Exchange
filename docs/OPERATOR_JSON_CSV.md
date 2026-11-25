# Operator: flat JSON string records to CSV

Base #79 081da9e451d2a8163a1b4e67581c7be5d6b0ddcc; Python 3.10/3.13 and Windows native/frozen/Genesis checks passed (45566470235).
New service: explicitly selected local UTF-8 JSON array of flat string-only records, 256 KiB input,
1–2000 rows, 1–16 exact declared columns, 256 characters per cell, unique nonempty trimmed key.
Reject missing/extra/duplicate members, nested values, numbers/booleans/null, formula-shaped or
control-containing cells. Preserve lexical strings (including leading zeroes); deterministic quoted
CSV sorted by key, declared column order, CRLF. No external tools, network, data cleansing or inference.
Verify input bytes and every output field independently of serialization; bind selected source
format, exact bytes, saved-plan scope and QA to immutable preview/export/registration pins.
Legacy CSV v2 contract/report and historical obligations retain their original format and checks.
JSON output is CSV; the same historical obligation and simulated-finance boundary applies.
Scout uses narrow literal JSON-to-CSV title hints only, never actual eligibility or buyer demand.
Native saved-plan button, explicit local file selection, re-preview before export or registration.
No real contracts, delivery dispatch, payment, zero-capital claims or external authority.
Tests cover exact output, unsafe/ambiguous source, format and byte pin, halt, registration/history,
Scout title and requirement assessment. Native GUI smoke also compares the two source formats.
