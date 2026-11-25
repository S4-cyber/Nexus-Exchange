# Native Aegis assumption evidence workspace (review candidate)

E14/E18/E22/E27/E35/E38: native local evidence review for exact saved scenarios. All assumptions and document contents remain unverified.

## Design and acceptance
- Open Aegis from the selected saved scenario, never from unsaved form values. Fixed scenario fingerprint and archived observation/profile context for the window.
- Display all 17 assumptions, canonical saved values, unknowns, per-field references and coverage distinct from independent verification.
- Explicitly select a field and a local file to attach, or select a reference and reselect a file for byte comparison. No file path, filename, raw bytes or extracted content retained in the evidence database. No automatic scanning, upload or network.
- Reload declared profile and exact plan scope for each action; pass cooperative halt to the bounded backend. Recheck profile before displaying the result. A concurrent profile change after a committed attachment may leave an immutable historical reference in the old scope, never a current-scope or authorization claim.
- Byte match/mismatch is ephemeral and distinct from source authentication or factual verification. Clear stale output on selection/refresh/error/observed halt. No approval or verification flag is elevated by references.
- Test-first 173674a5f38057ed67ae2e822ff5d6a88889faa8; run 45543585916 observed expected missing evidence_workspace import.
- Controller and Tk window 9596d8ae3502f4f39861f40ea08af5febfd7fc16; scenario editor integration 0ed5e834c44a3572392be68dc3eeba28e6e818e1; Windows workflow 63f943d94d3d4ee4fc498f761c13f7aa5445f1d6. Eight new controller/presentation tests, plus populated GUI attach/reload/match/mismatch and privacy smoke. Python 3.13 controller job 138968003359 observed 310 passing tests. Exact integrated/frozen checks pending at entry.

## Reference audit
Nexus Operative read-only nexus/journal.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: bounded hashed storage without credentials; architecture only, no trading code copied. OCDS eb57a46e69efead6ae62144fe1b7cefc53d07ff2: Document relatedItems/dateModified, Apache-2.0 license and doc dependencies inspected; no upstream dependency adopted. Context7 CPython 3.13.14 Tk/ttk/filedialog reference reviewed for APIs compatible with Python 3.10. Agency-agents adaptation and Exchange #2 / Operative #116 reviewed; no agent assertion grants privilege.

## Limits and next steps
Single-user local archive; synchronous bounded reads on Tk thread and cooperative halt, not immediate cancellation during blocked callbacks. No authenticated reviewer or independent factual verification, live outreach, bids, contracts, payments or signatures. No new dependencies or paid resources. Prior Aegis head 730a6762d751c10ef22c1627a92acff96a4d0bd5 passed 302 tests (45543009854). Prior Governor Windows preview ddd813014d91fee6ba2055d6064de86481fba322 passed frozen GUI smoke (45542186400, artifact 14988869680). Main formal acceptance 0/42. Next: criterion-based independent evidence review, bounded Council delegation, performance and release consolidation.
