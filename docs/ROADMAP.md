# Nexus Exchange — Development Roadmap

## Product boundary
Nexus Exchange is a standalone, initially research-only commercial opportunity platform. It does not own or warehouse assets, custody client funds, or represent itself as a licensed broker. All binding contracts, signatures, payments, bid submissions, and other regulated actions require validated legal authority and explicit approval.

## Reference repository
[Nexus Operative](https://github.com/S4-cyber/Nexus-Operative), inspected at review/v0.340.381-cross-session-coverage. Its main branch currently contains build request markers rather than the working source tree. Do not copy source from main assuming that it represents the latest working implementation.

### Reuse audit — first pass
- `nexus/council.py`: deterministic trading-specific evaluators and veto rules; use its pure-function/reason-code pattern, not trading heuristics.
- `nexus/risk_gate.py`: strict schema and fail-closed admission pattern; do not port paper-order or broker logic.
- `nexus/journal.py`: bounded SQLite research journal with persistence protections; adapt only after review, retaining security invariants.
- The above are **candidates**, not ported modules; source functionality, dependencies, licensing, tests, and security must be validated before reuse.

## Milestones
| Stage | Deliverable | Acceptance evidence | Status |
| --- | --- | --- | --- |
| M0 | Public-safe repository, scope and roadmap | README and roadmap committed | In progress |
| M1 | Scout: normalized opportunity schema | Unit tests for identifiers, provenance, malformed inputs and deduplication | Pending |
| M2 | Read-only procurement connector | Mock + authorized public-source sample contract data, rate limiting, retry behavior | Pending |
| M3 | Council review interface | Reason-coded assessments, missing evidence request, immutable review outcome | Pending |
| M4 | Durable memory | Database migrations, tenant isolation, auditable activity log, retention | Pending |
| M5 | Atlas supply/demand matching | Qualified counterparties, ranking and source citations | Pending |
| M6 | Diplomat draft-only correspondence | Verified recipient, draft archive, consent and anti-spam controls | Pending |
| M7 | Operator sandbox | Browser/document mock workflows with approval gates | Pending |
| M8 | Simulated deal lifecycle | Discovery through mock invoice and reconciliation, no real transactions | Pending |
| M9 | Production readiness | Security review, CI, observability, legal/process validation, documented operator controls | Pending |

## Hourly sprint protocol
1. Read current branch, open PRs, roadmap and failing CI before selecting work.
2. Select the smallest high-impact milestone and identify dependencies.
3. Prefer test-driven, self-contained changes in isolated branches; use a draft PR.
4. Record source permissions/provenance and test evidence.
5. Never merge unverified work or report passing tests without observed output.
6. Update roadmap and status with real commit/PR identifiers and remaining blockers.
7. Maintain independent development and release cadence from Nexus Operative.

## Technical design choice — proposed
Python for Scout/validation agents, PostgreSQL/Supabase for later persistent storage, REST/JSON interfaces, and an independently deployed web UI. Avoid paid services or production accounts until viability is demonstrated.

## Immediate next work
Implement a deterministic, offline Scout normalization and deduplication library with test fixtures. No outreach or external API keys required.

## Granular release gates (each gate requires observed evidence)
Status: M0 repository and roadmap present; all implementation gates below pending until verified. Gate completion is binary; do not infer completion from version numbers.
| Gate | Deliverable / acceptance test |
|---|---|
| E01 | Repository inventory and pinned reuse-source commit |
| E02 | Reuse dependency, license and security audit |
| E03 | Reproducible local test command |
| E04 | CI executes unit tests on pull requests |
| E05 | Opportunity schema rejects malformed input |
| E06 | Source URL and retrieval timestamp preserved |
| E07 | Stable identifiers and duplicate detection |
| E08 | Currency and deadline normalization |
| E09 | Offline procurement fixtures |
| E10 | Read-only procurement adapter |
| E11 | Rate limits, retries and pagination |
| E12 | Source failure and stale-data handling |
| E13 | Council deterministic scoring |
| E14 | Missing evidence and rejection reason codes |
| E15 | Council task delegation and bounded retries |
| E16 | Governor default-deny action policy |
| E17 | Emergency halt and restart tests |
| E18 | Persistent opportunity and event storage |
| E19 | Database migration and access isolation tests |
| E20 | Buyer/supplier profile schema |
| E21 | Supply-demand matching and qualification |
| E22 | Cost, fee and probability-adjusted return calculation |
| E23 | Property intelligence adapter and licensing gate |
| E24 | Draft-only quotation request generation |
| E25 | Correspondence thread and recipient verification |
| E26 | Browser sandbox with allowlisted domains |
| E27 | Document extraction and untrusted-input isolation |
| E28 | Contract template and obligation tracking |
| E29 | Signature sandbox and authority verification |
| E30 | Mock invoice and reconciliation |
| E31 | Idempotency and interrupted workflow recovery |
| E32 | End-to-end simulated deal with audit trail |
| E33 | Dashboard opportunity Matrix |
| E34 | Council and activity dashboard |
| E35 | Revenue and exposure dashboard |
| E36 | Authentication and role authorization |
| E37 | Security, dependency and secret scanning |
| E38 | Performance and failure-injection tests |
| E39 | Preview deployment and end-to-end smoke tests |
| E40 | Release packaging, runbook and recovery drill |
| E41 | Independent legal and commercial readiness review |
| E42 | Verified release candidate; live operations remain gated |

## Shared engineering directive
Use relevant installed plugins where access and task fit are confirmed: Superpowers for planning/TDD/review, GitHub for source and CI, Linear for milestones, Supabase for isolated database work, Vercel for previews, Figma for design, PostHog for observability, TinyFish for permitted browser research/testing, Gmail/Drive/Calendar/Contacts/DocuSign for sandbox or authorized commercial integration. Do not force irrelevant calls, copy secrets, expose private data in public repositories, incur unapproved costs, or mistake installed plugins for runtime credentials. Maximize useful work within available time, context and tool limits; batch independent reads, parallelize isolated tasks when supported, and avoid redundant scans. Prioritize implementation and verification over status-only commits. Each report must identify completed gate IDs, changed files, exact commit/PR, observed tests, remaining blockers, next gate and verified gate count out of 42. Keep Nexus Operative independent and read-only as a reuse source during Exchange work.

## Sprint 01 — candidate evidence (review branch)
- E01: repository inventory and Operative reference pinned in docs/SCOUT_FOUNDATION.md.
- E02: preliminary audit; licensing and full security review remain pending. No code copied.
- E03, E05–E09: Scout implementation and offline fixtures tested locally (six tests); require matching remote blobs and integration review before recording on main.
- E04: workflow added; hosted execution not yet observed.
- Verified main implementation gates: 0/42 until integration. Candidate locally supported gates: E01, E03, E05–E09 (7/42).
- Next: CI evidence, review source identity and malformed inputs, then authorized read-only procurement adapter E10–E12.


## Sprint 02 — Governor offline policy (review branch, 2026-11-24)

- Prior Scout head 874595bbf0d6d6c1be357a641c9b8570e9b51f0d: [CI run 45506712076](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45506712076), Python 3.10 and 3.13 unit steps successful.
- Separate handoff head 64b1790b1f01c5a69eaf4e65518393bdb0be0e64: [CI run 45507767681](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45507767681), both Python jobs successful. E15 remains a candidate; independent evidence verification and integration are outstanding.
- E16 candidate: new pure policy permits only explicitly enumerated local research, evaluation, draft creation and simulation when halt state is exactly False. Unknown action/state and all external actions deny; no approvals, live connectors, custody or inventory paths. E17 only partially covered: snapshot halt precedence and offline restart tested; trusted persisted halt state, authenticated restart and dispatch enforcement remain unimplemented.
- Local Python 3.13: six new unit tests passed after initial missing-module failure; exact local and remote source/test blob IDs verified (119a2cc295d6d6fb0333684fa830683836f332dd, 6da477ba5a523a54c055a5df27f6fc35839aa16f). Combined hosted CI for this branch remains pending at documentation time.
- Reuse: inspected pinned Operative risk_gate.py (6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11) for default-deny concepts. No source copied and no trading code imported; E02 remains pending.
- Review-only stack on Scout PR #1; no merge, no external actions, no new cloud resources. Vercel returned no teams; Supabase no projects. Main verified gate count remains 0/42 pending integration; Scout branch has eight evidence-supported candidates E01, E03–E09, and this increment adds E16 as a local candidate only. Next: review source identity/URL redaction, finish authorized procurement adapter E10–E12, then wire Governor at a trusted boundary before enabling any external tool.

## 2026-11-24 — desktop and local archive review evidence
- Formal accepted gates: 0/42 on main; draft-branch evidence is not release acceptance. E03/E04: reproducible unittest and PR CI evidenced by run 45522722177 (Python 3.10/3.13 passed); E05–E09, E16, E17 and E34 have supporting offline tests on the stacked review branches, awaiting integration and acceptance. E17 still requires restart-safe halt and interactive controls testing.
- E40 partial: Windows artifact 14979949622, run 45522718647, for b66d9ec; portable preview only. Installer, signing, recovery drill, graphical smoke tests and release promotion pending.
- E18/E31: PR #15 introduces bounded historical opportunity observations, idempotent writes and atomic conflict rollback; re-screen on read at explicit time. Test-first commit 486a1f7; implementation f25bbd2; timestamp correction 9c69e2f. Do not use historical observations as an active tender index, or treat historical eligibility as permission. Separate concurrent PR #14 work adds a review result journal; reconcile shared storage boundaries before integrating, not two competing stores for the same function. CI and migration/access isolation (E19) pending.
- Reuse audit: inspected Nexus Operative nexus/journal.py blob 59ee08e7734347897b29af33603dffba783ec9ad at review/v0.340.381-cross-session-coverage; adopted bounded rows, explicit transactions and payload minimization as architectural ideas, not source copying. No trading logic or credentials.
- OCDS Merge pinned a75d1f6d5d2dc413c4ca6c83646af41d9e839e9c: inspected LICENSE, pyproject.toml, ocdsmerge/merge.py. BSD-3-Clause, 0.8.0, requires Python >=3.11, jsonref/requests. Defer adoption because current CI includes Python 3.10, transitive audit incomplete and default schema resolution may involve remote resources. No dependency installed.
- Next: reconcile review and observation stores, verify CI and GUI, add process-level recovery, durable halt and approved offline imports. Source compilation and opportunity lifecycle must precede live source collection.


## Desktop archive integration candidate
- E18/E31: PR #15 head db0c7028e4fd8422ccf55ff087b9e3ea963999cf passed PR CI run 45522958078. Adopt its bounded observation archive as the desktop's canonical storage candidate; do not wire the parallel ReviewStore or persist an eligibility decision as ongoing authority. The two review branches diverged; reconcile on integration, no data migration or deletion performed.
- E33/E34: desktop task worker writes historical observations before marking success. A separate archive window searches the newest 100 observations, re-screens at explicit current time, and exports the displayed report as JSON. Synthetic data only; source data is not verified. Historical observations are not an active opportunity index. Halt is cooperative and can occur during an already-started local archive transaction; no external actions.
- E38–E40: three new integration regression tests, source/frozen GUI construction smoke tests, Windows x64 artifact workflow for review/desktop-opportunity-browser. Hosted results pending at this entry. Installer/signing, recovery, sustained concurrency and actual user-machine GUI tests remain pending.
- Main accepted gates remain 0/42. Next: review and consolidate PR stack, durable halt/recovery, authorized offline file import, source-specific collection adapter, then counterparty qualification.


## Offline procurement import candidate
- E05–E09/E12/E18: user-selected UTF-8 JSON manifest, bounded to 2 MiB and 100 compiled snapshots, strict duplicate-member and numeric handling, explicit asserted source URL and retrieval timestamp. Reject incremental releases, unknown schemas, future retrieval, and invalid or inactive tenders. All-or-nothing batch validation, no HTTP requests or external actions. Source assertions are not independently verified.
- E33/E34: desktop Import compiled JSON control invokes the existing Governor, pipeline, task journal and opportunity archive. Halt disables new imports; already-started local work remains cooperatively cancellable.
- E38–E40: seven new import regression tests; Windows packaging includes this branch, source/frozen GUI smoke checks. Hosted results pending at entry time.
- Reuse decision: follow OCDS record/compiled release distinction (https://standard.open-contracting.org/latest/en/schema/records_reference/ and https://standard.open-contracting.org/latest/en/schema/merging/). No new dependency or upstream code copying. Full OCDS schema validation, upstream compiler integration, source authentication, raw file digest persistence and provider-specific collection remain pending.
- Formal main acceptance remains 0/42. Next: reconcile draft stack, durable halt/recovery, buyer/supplier qualification and an authorized read-only procurement adapter.


## Atlas qualification candidate
- E20/E21: normalized source-asserted buyer/supplier profiles; scheme-scoped identity; explicit classification and region; deterministic candidate matching with reason codes for roles, same identity, capacity, currency, geography, stale/future observations and Council opportunity screening. Governor denies evaluation when halted or unknown.
- E38: ten new regression test methods for offline matching, schema rejection, bounded batches, provenance, exact financial constraints and halt precedence. CI pending at entry time.
- Reuse: OCDS v1.1.5 organization identifiers, party roles and classification schema inform the design. No upstream code copied or new dependency installed; see docs/ATLAS.md.
- E22 remains pending: declared capacity and tender amount are not quotes, revenue or economic forecasts. E20/E21 remain partial until verified organization/source linkage, profile persistence and user interface are implemented.
- Prior E40 evidence: import-enabled Windows build 45523381631 completed successfully, including GUI smoke checks and artifact 14980484368. Formal main acceptance remains 0/42; integration stack not merged.
- Next: integrate Atlas with archive and explicit user requirements, persistent halt/recovery, then source adapters and evidence-based economics.


## Fee-only scenario economics candidate
- Prior Atlas head 030919eff3b46d3d6980d97f9f3473181c3a3d7c passed PR CI run 45523816491 (67-test code suite previously observed passing on 45523776844).
- E22: explicit fee, upfront and completion cost, conditional collection probability, completion probability and modeled exposure limit. Decimal arithmetic; no tender budget treated as revenue; Atlas reasons are preserved; Governor blocks simulation when halted/unknown. Nonpositive expected net or excessive modeled loss blocks review eligibility. No financial commitment or authority.
- E38: ten new regression test methods, including low ambient precision, failed matching, zero completion, input validation and halt precedence. Test-first commit 7b448b8; implementation 37edfe0. CI for the implementation pending at documentation time.
- Reuse: existing Atlas, Governor and Scout, Python Decimal context. No third-party dependency or code copy; no additional spending. See docs/ECONOMICS.md for formulas, assumptions and limitations.
- E22 remains partial: assumption evidence, legal liability modeling, UI integration, scenario persistence and actual quote verification pending. E20/E21 remain partial pending source verification and desktop integration. Main accepted gates remain 0/42; all implementation branches are review candidates.
- Next: local scenario input bound to archived observations, integrate Atlas/economics into Windows preview; consolidate branch stack; durable halt and recovery; permitted source collection.


## Desktop deal simulator candidate
- E20–E22/E33–E34: imported scenario resolves an exact latest historical observation among newest 100 rows for the selected release-scoped key; Atlas and fee-only economics evaluate at explicit current time. Report includes raw input SHA-256, normalized source assertion, profiles, terms, exact-decimal results and reasons. No live transaction authority.
- E18/E31: existing task journal records completion/cancellation/failure; report export is explicit JSON; full automatic scenario persistence and cross-release supersession still pending.
- E38–E40: seven additional scenario/integration test methods; Windows packaging branch enabled with existing source and frozen GUI smoke checks. Results pending at entry. Prior economics head 215d44c1c579ee6006c6a20c19bfb200e4359148 passed CI run 45527912902.
- Reuses existing Governor, archive, strict import helpers, Atlas, economics and desktop journal. No new runtime dependencies or external actions.
- Main formal accepted gates remain 0/42; consolidate review stack and verify full integrated build before release. Next: review and consolidate, persistent halt/restart recovery, source-specific collection and independently verified counterparty/quote evidence.


## Integrated offline baseline review
- Consolidate the tested desktop simulator (d4e56a114862736e658eb11640917cae71cb7413) and independent handoff/research/protocol branches into a single main-targeting integration candidate. Preserve bounded archive, exclude parallel review-result store, consolidate CI and update README. See docs/INTEGRATION_BASELINE.md.
- Prior desktop simulator Windows run 45528842172 completed successfully, artifact 14983957296. New combined test suite expected 91; exact-head CI pending.
- E15: hardened non-privileged handoff scaffold, independent evidence verifier and actual delegation remain pending. E03/E04/E38/E40: consolidated verification required. Formal main accepted gates remain 0/42 until review and promotion.


## Owner directive — dual revenue pathway and native Scout internet workspace
- See docs/REVENUE_PATHWAYS.md; R01–R10 are granular subgates of existing E01–E42, not additional release gates. Genesis starts at $0, Catalyst models an optional owner-defined budget; earned revenue is separate from restricted funding. Prioritize demonstrably zero pre-payment cash exposure, digital deliverability, independently verifiable eligibility and evidence.
- R01/R02 candidate: native Scout pathway planning and checklist UI, fixed official SAM/SBA/Grants source links, cost/authority gates, seven new regression tests. User click opens default browser; embedded browser and automated acquisition remain pending. No bank connected or transfer enabled. Checkboxes are assertions only, not permissions.
- R03 next: official SAM public API adapter with secure key handling, quotas, bounded pagination, read-only authorization and explicit source verification. R04/R05: secure owner profile and persistent lead-specific evidence/checklists.
- Prior consolidated baseline 6c8f5e5aa1cf971c7a9fc7235d788b3a1e6b3ef4 passed Windows run 45529112749 and unit run 45529126511, still draft PR #21. Main acceptance remains 0/42; no new formal gate acceptance.


## SAM read-only source pilot candidate
- R03/E10–E12: official SAM v2 search transport fixed to HTTPS GET, explicit owner consent and cooperative halt, 3-request cap including a single transient retry, 25 rows/page, paced pagination, strict bounded JSON validation, no redirect or contact-data retention, sanitized errors and key-echo rejection. Native masked per-search key prompt; key not saved. Live request not yet tested/authorized. No automatic polling or durable quota enforcement.
- R05/R06/E14/E33: per-notice evidence To Do and research-only deadline/type ordering; no execution eligibility or known cash exposure. Native results window and export; evidence persistence and independent validation remain pending.
- R07: explicit official notice browser link, no embedded browser yet. No live application submission, bid, outreach, funding or payment capability.
- E38: 12 new SAM test methods. Observed 110/110 tests on Python 3.13 and both Python jobs successful at 610634d5fd135750000e86eba4c7b445b8c1c554, run 45530331128. GUI results and exact-head build pending at documentation time.
- Prior revenue pathways exact-head Windows build 45529794634 succeeded, artifact 14983629079. Main formal acceptance remains 0/42. Next: verified owner profile and secure local credential handling, persistent evidence checklists, SAM live pilot only with explicit consent and own key, then approved automated read-only cadence.


## Global trade diversification directive
- See docs/GLOBAL_TRADE_REGISTRY.md. S01–S07 subgates map to R/E gates; preserve E01–E42 denominator. Catalog 24 primary-source-documented channels and 17 commercial routes. Distinguish earned work, restricted funding, prizes, intelligence and compliance. User-initiated official links; source prerequisites and hard research-only brokerage holds; no new live connectors.
- S01 candidate: native catalog/route windows, filters and 12 regression methods. Current exact-head tests and packaging pending. Prior SAM read-only head c6b32aec191dddc2cc67a96ebedefb1478a27948 passed Windows 45530452026 (artifact 14985045588) and PR CI 45530464697. No authorized real SAM request yet.
- S02 next: public EU TED and UK OCDS plus CanadaBuys, then USAspending contractor intelligence, ITA/World Bank leads, approved private and local sources. Treat licensing, cash exposure and authority as unresolved until independently verified. No new paid dependencies; main acceptance remains 0/42 pending integration.


## Keyless TED Scout pilot
- S02/R03/E10–E12 candidate: fixed anonymous TED v3 search, CPV and date filters, three-request cap, provenance, conservative tender classification, native source search and lead-specific checklists. Eleven mocked test methods; exact-head CI/build pending. No key required, no submission, no execution, no known cash exposure.
- Previous Global Trade candidate 8fa86250520d585b853cf22bd44e3731ce94f2f0 passed 122-test CI and Windows 45531247704 (artifact 14984487891). Consolidation and formal release gate acceptance still pending. Next: authorized real TED response/schema validation, UK OCDS/Canada public sources, lead-bound evidence/profile persistence, independent review.


## UK Find a Tender release pilot
- S02/R03/E10–E12: anonymous official UK OCDS release-package collection candidate, frozen update window, same-origin cursor validation, bounded requests, source-scoped release identity, lifecycle-aware blocking and native source search. Thirteen new mocked regression methods; exact-head results pending.
- E14/R05: historical tender events generate verification tasks; reject superseded, ambiguous, incomplete-window and non-active events. Full record rehydration, current-state compilation, persistent source evidence and independent eligibility/cash exposure verification remain pending. Official help returned 403; parameters corroborated by published secondary documentation, not live provider tests.
- Prior TED head e31ac801ff8e7d25958b970ea92e55c0417e7767 passed 133-test CI (45531803268, 45531817458) and Windows run 45531803354 (artifact 14984567823). No new paid dependencies. Main accepted gates 0/42 pending integration; next: CanadaBuys, source lifecycle reconstruction and unified lead archive.


## CanadaBuys keyless dataset pilot
- S02/R03/E10–E12: fixed public open-tender CSV download with one-request budget, bounded strict bilingual parsing, transport freshness, timezone-conservative deadline screening, schema drift and duplicate checks; native search/result/checklist UI. Twelve new regression methods; exact-head CI and Windows build pending.
- Reuse: pinned Maple Procure 21bd93119fd6fe2300361ac3cc6be13024af21a0 (MIT) reviewed for factual CSV schema and provenance architecture only. Official data dictionary unavailable in research environment; live schema validation required. No new dependencies or paid service.
- Prior UK FTS exact-head Windows run 45532095669 succeeded; artifact 14985632150. Unit suite 146 passing at 45532095611/45532107958.
- Main formal acceptance 0/42. Next: unify source reports into bounded persistent lead archive and add USAspending award/subaward intelligence; verify actual provider connectivity, source data lifecycle and owner evidence before promotion.


## Unified Scout historical lead memory
- R05/R06/E18/E31/E33: unified source-scoped historical observation store for four procurement adapters, automatic guarded persistence before successful task logging, bounded SQLite transactions, canonical report projection, replay and conflict protection, source/title search and explicit export. Historical display rechecks stale/expired records and known later UK events; no previous eligibility or authority persisted as current. Nine new regression methods; CI/build pending.
- Previous CanadaBuys candidate 45bc03d707d468bf75d3a1552b796aca00a98dbd passed 158 tests (45532423219) and Windows 45532423258 (artifact 14985557823). No new dependencies or paid service. Existing compiled OCDS archive unchanged. Main accepted gates remain 0/42.
- Next: live source validation and lifecycle reconciliation, USAspending contractor intelligence, durable lead-bound To Do and owner profile evidence, safe restart/interrupt handling, consolidation. See docs/SCOUT_LEAD_MEMORY.md.


## USAspending contractor intelligence pilot
- S03/R03/R05/E10–E12/E18/E20: bounded official prime-award search by NAICS and signed-date range; preserve contractor and award identity separately from active tenders, never award amounts as revenue. Native search, source-specific checklist and unified historical memory. Ten regression methods; CI/build pending at entry.
- Reuse official USAspending API contract pinned 24290f79dbec0e07238cd4e890a9e3ef6044d984 (CC0). No upstream code copied. No actual provider request, paid service or commercial dispatch during development. Next: authorized live validation, subaward discovery, owner capability/profile and durable evidence tasks.
- Prior unified lead memory head ac7c4184e3129579d7cbd5762d2bd4713679f4c1: 167 tests passed; Windows 45532680488 artifact 14985935006 passed. Main formal acceptance remains 0/42 pending consolidation/review.


## Declared owner capabilities and Scout review ordering
- R04/R05/R06/E20/E21/E33: local owner planning profile with explicit save/clear, source and availability preferences, NAICS/CPV/keyword matching, profile revision, source-backed classification retention and native ranked historical view. Ten new regression methods; exact-head CI and Windows build pending.
- Every profile is self-declared, not identity, authority, bank balance or verified capability. Historical blockers and award intelligence are preserved. Existing stored records remain readable. Actual evidence-bound durable owner checklist completion, encrypted credential storage, verified entity linkage and executable zero-cash ranking remain pending.
- Prior USAspending candidate f877bf70176d18f5009496ed7b6f9dde5bad13b3 passed 177 tests (45533021295) and Windows 45533021285, artifact 14986065268. No new dependencies. Main formal acceptance remains 0/42 pending consolidation.


## Persistent lead-specific owner To Do candidate
- R05/E14/E18/E31/E33: durable owner review notes bound to exact archived observation and optional owner profile content revision. Shared task definitions, bounded SQLite state, exact-key lookup, canonical digest, optimistic concurrency, native review window. Eleven new regression methods; CI/build pending. Evidence noted never implies independent verification or action authority.
- Prior owner capability head 60ecafb158e0e3b42665b9b0527b7253a9fd492f: 187 tests passed on Python 3.10/3.13 (45533543623); Windows 45533543654 artifact 14985559564 passed. Draft PR #31. No new dependencies or paid services. Main accepted gates 0/42.
- Next: independently verifiable evidence and scoped approval records, cash-exposure and delivery-feasibility evaluation, durable halt/recovery, live source validation and branch consolidation. See docs/PERSISTENT_TODO.md.

- Verification: exact head ea8e6e4a4b07b68f7a8cfc8fa68b0b88025c2f91 passed 198 unit tests on Python 3.10/3.13 (45536283675), and Windows unit tests passed, but Windows GUI smoke 45536283733 failed during cleanup because the synthetic fixture shadowed the event-store variable. Corrected fixture variable and strengthened GUI smoke to save/reload an evidence reference. Replacement exact-head build pending.


## Aegis evidence fingerprint candidate
- R05/E14/E18/E27/E31: owner-selected local file fingerprint references tied through the existing checklist scope; reselect and compare saved SHA-256/length; no persistence of raw file or path, no independent factual verification or action authority. Ten regression methods and populated GUI smoke covering save/reload/compare. Exact-head CI/build pending.
- Prior corrected persistent To Do head 7996aa6cc92bf0b523654954021dec84caeb03c0 passed Windows 45536372110 (artifact 14986998694) and CI 45536372118/45536379549. Existing local profiles and notes remain unchanged; no new dependencies or paid services. Main acceptance 0/42 pending integration.
- Next: authenticated source evidence, explicit delivery requirements and feasibility/cash exposure scenarios, scoped approvals, durable halt and recovery. See docs/AEGIS_FILE_EVIDENCE.md.

- Verification: Linux Python 3.13 passed 208 tests at 96a64366c8a10e59fa0cfb7865f7feacbf09db64 (45536623922). Windows 45536623953 failed a fingerprint test because path and handle metadata comparisons differed after file modification. Revised cross-API comparison to stable identity/size, with before/after metadata checks within each API. Added regression methods for metadata precision and filesystem permission error redaction; replacement CI and GUI build pending.


## Scout cash feasibility candidate
- R06/E22/E35: local lead/profile-bound USD scenario, explicit unknown cost categories, conservative pre-payment exposure, expected net with conditional payment, modeled labor and payment timing. Nine regression methods; exact-head CI pending. No verified revenue, cash balance, delivery schedule or commercial authority. See docs/SCOUT_CASH_FEASIBILITY.md. Main accepted gates remain 0/42.
- Next: independently sourced terms and costs, persistent scenario review/UI, current deadline and delivery checks, durable halt/recovery and branch consolidation.
