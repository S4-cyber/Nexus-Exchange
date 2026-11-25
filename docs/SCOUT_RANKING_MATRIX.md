# Native Scout ranked opportunity Matrix (review candidate)

R06/E33/E35/E38: desktop presentation of the existing bounded deterministic ranking engine. Historical observations and all hypothetical financial and timing inputs remain unverified; the display grants no execution authority.

## Acceptance and design
- The native Matrix is accessible from the desktop and Scout lead history. Explicit refresh reloads the saved declared owner profile, calls RankingStore once for a bounded consistent archive snapshot, and checks the profile revision and halt state before returning.
- Source and title filters, displayed row limits, scan/display truncation, exact snapshot UTC and evaluated/matched counts remain visible. Filter changes clear the prior snapshot. The report explicitly does not claim global ranking.
- Preserve backend order, source review holds, unresolved assumptions and contractor-only classifications. Show modeled USD exposure/net without rounding nonzero values to zero; collection wait is rounded up to elapsed hours for presentation only.
- Selected row details identify the archived observation, declared profile revision, saved plan fingerprint, underlying model, current snapshot reason codes and explicit unverified status. Navigation resolves the exact current archived observation/profile context before opening local scenario planning or owner review To Do. Navigation does not act on a saved ranking verdict.
- The halt check gates refresh and navigation; a Tk timer clears the Matrix display when it observes a halted/unknown state. No credentials, external calls, payments, bids, outreach, offers or signatures.
- Profile rechecks around local reads are not a cross-database atomic authentication or authorization system. The desktop remains single-user, local and synchronous. Independent factual evidence, durable halt/recovery, multi-tenant storage, performance stress and independent release review are pending.

## Implementation and verification
- Test-first 9dfb10c3be0d66a8e0b3cb3e30acedea2c1174e2; run 45541245249 observed expected missing ranking_workspace import.
- Controller and presentation 5cffc5ec61492d383f06aa3dc21458515b3136e2; run 45541324514, jobs 138960277686 and 138960278017: 276/276 tests passed on both Python 3.10 and 3.13. Eight new regression methods cover refresh/order, bounds/filtering, supersession, profile changes, halt/missing profile, stale data, exact numeric formatting and profile race rejection.
- Desktop integration d5ff254f2c1c393404a49b33f9d0aebefb1aa30a and Windows CI wiring db9c4a62b5a4c04f52692a0a805446b6ed196538. Populated GUI smoke exercises actual archived scenario, source hold, unverified display, exact-context navigation and filter invalidation. Exact integrated and frozen executable checks required before claiming a replacement preview.
- Baseline rank revision d9aab09933b4429c7e6cf22920e418b43d1ab6a2 passed 268 tests, run 45540933057. Previous native scenario executable e8da3635a04ba466fe7e4227758b1a610a3cd05f verified at run 45539178809, artifact 14988731479. Draft PR #39; formal main acceptance remains 0/42.

## Reference audit and boundaries
- Nexus Operative read-only nexus/council.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: retain deterministic reason codes and veto precedence as architectural concepts; no trading code or credentials copied.
- OCDS standard eb57a46e69efead6ae62144fe1b7cefc53d07ff2: inspected Classification and Period definitions, Apache-2.0 license and documentation dependencies. Scheme-scoped classifications and explicit missing times remain source assertions. No new code or dependency adopted; transitive/security review needed before adoption.
- Context7 CPython 3.13.14 Tk/ttk reference reviewed for Treeview selection, scrollbars and virtual events. Existing Python 3.10-compatible standard library retained.
- Agency-agents adaptation and Exchange PR #2 / Operative PR #116 reviewed; no agent verdict or evidence assertion grants privileges. No new infrastructure or dependency.

Next: durable restart-safe halt and interrupted-task recovery, independently checkable evidence for financial assumptions, guarded Council review, and consolidation toward formal release.
