# Native scoped registration and recovered Genesis provenance

Base RC2 #89 24676b9df401682ebcbb4b1f3bde1b9ae044e385 passed Python push/PR and Windows checks
(45633801107, 45633817390, 45633817468). The same main-targeting review
branch is advanced by a single compare-and-swap commit, not merged.

The Scout requirements form now offers **Register exact sample** after a
successful exact scoped local preview. Export and registration are separate
confirmed actions consuming the same preview; after export, re-review and
re-preview before registration. Form edits, busy/halt and stale selection
invalidate both actions. The existing runtime repeats the scoped production,
matches the artifact fingerprint, rechecks review and saves exact provenance.
The UI validates the returned historical obligation, plan/context, Scout
scope and all three preview pins. Legacy obligations are not treated as
scoped. A callback error after registration can leave a durable record;
inspect history before retrying. No file paths or source content are
persisted by the registration. Existing database tables are retained.

The owned Genesis lifecycle keeps the existing legacy export negative-control
and adds exact scoped preview, export and registration of a separate matching
local artifact before simulated acceptance, invoice, partial receipt, backup,
restore and settlement. The recovered obligation must retain its original
Scout provenance, and stale re-registration must fail without changing it.
The source diagnostic and Windows bundle verifier require the new check
names and scope/review hashes. Existing unsigned bundles remain evidence of
their own prior revision, not this stricter diagnostic. No real customers,
external actions or income. No new dependencies, services or changes to
Nexus Operative. Three new test methods plus extended native/frozen and
Genesis regression coverage. Exact-head hosted verification required.
Independent review, authorized live-source validation, actual recipient
verification, licensing, signed installer and formal gate acceptance remain
outstanding. Main remains unchanged, 0/42 formally accepted.
