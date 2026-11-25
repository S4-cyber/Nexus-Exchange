# Per-assumption Aegis evidence bindings (review candidate)

E14/E18/E22/E27/E31/E38: independently checkable file-byte integrity for each known immutable financial/schedule assumption. No claim that file content establishes a commercial fact.

## Implementation plan and acceptance
- Extend the same single-user SQLite scenario archive with a separate immutable evidence association table. Bind canonical field/value digest, exact plan ID, byte fingerprint, and recorded UTC time. 17 assumption fields; do not bind a document to an unknown value or implicitly replace unknowns with zero.
- Explicitly selected local file is hashed using existing Aegis bounded/cooperative fingerprinting. Store no path, name, raw content or credentials. Canonical evidence ID excludes creation time so repeated same-byte attachment is idempotent. Different assumption, plan or file bytes cannot share an ID. Cap at three references per field and 20,000 rows total; no auto-pruning.
- Resolve and validate current archived observation/profile and saved-plan creation time before file access and recheck within the transaction after hashing. Bind only after successful checks. Scope changes, halt, integrity errors, clock regression or capacity failure reject without writing.
- Coverage distinguishes unknown assumption, known but unreferenced, and reference noted/unverified. Coverage counts only references, never verified facts. Recheck bytes against the exact saved reference on explicit file reselection, with current scope and halt checks before and after. Do not persist the byte-match verdict as current or elevate it into approval or factual verification.
- Test before implementation; run both hosted Python versions. No desktop integration or new executable claimed for this backend increment. Independent factual/issuer verification, reviewer identity, per-assumption UI, stress and retention controls, Council evidence evaluation and release consolidation remain pending.

## Reference audit
Nexus Operative read-only nexus/journal.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: bounded storage and canonical hashed audit data; no trading code or credentials copied. OCDS standard eb57a46e69efead6ae62144fe1b7cefc53d07ff2: Document schema (ID, revision dates, related items), Apache-2.0 LICENSE and doc build dependencies inspected; documents can relate to distinct items without certifying them. No upstream dependency adoption; full security/compatibility review required before adoption. Context7 CPython 3.13.14 sqlite3 explicit transaction control reviewed; Python 3.10-compatible APIs. Agency-agents adaptation and Exchange #2 / Operative #116 reviewed; file references do not grant authority, and no agent verdict is trusted as independent verification.

Trusted local directory only. File fingerprints are not signatures; a malicious filesystem/database owner may alter data and identifiers. No live operations, paid infrastructure or new dependencies. Formal main acceptance remains 0/42.
