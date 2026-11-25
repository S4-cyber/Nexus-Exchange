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


## Scout schedule feasibility candidate
- R06/E14/E22/E35: separate historical submission cutoff from explicit hypothetical contract start and delivery due date; bounded preparation and delivery timelines, unknown propagation, elapsed UTC comparisons, average capacity, chronology and scenario-bound fingerprint. No award, submission, income, authority or factual verification inferred. Twelve new regression methods; code-and-tests head 9c4a41cbd46bf943124ad4cd0ef7c0b431223982 passed 231/231 tests on Python 3.10 and 3.13 (CI run 45537285674; jobs 138946875322 and 138946875717). Documentation-only successors require their own exact-head verification. See docs/SCOUT_SCHEDULE_FEASIBILITY.md.
- Baseline cash-feasibility head 777bb1a008bc24c97e75936008069e3e28bdd79b: 219 tests observed passing on Python 3.13; Python 3.10 and 3.13 jobs successful (45536781440 and 45536787270). Test-first schedule run 45537180101 produced the expected missing-module error. Implementation 54b718016e54107a3fceac99615f0f0d973da748, fixture coverage 9c4a41cbd46bf943124ad4cd0ef7c0b431223982. Draft PR #35.
- Main acceptance remains 0/42; no new dependencies or paid infrastructure. Next: persist scenarios with archive identity and evidence, desktop review, durable halt/recovery, branch consolidation and independent QA.


## Persistent Scout scenario candidate
- R06/E18/E22/E31/E35: immutable canonical financial and timing assumptions scoped to exact archive observation and owner profile revision; same SQLite transaction for lookup and insertion, bounded capacity and scoped listings, replay protection, digest checks, current re-evaluation and explicit supersession rejection. No prior verdict or authority stored. Fifteen new regression methods; code/test revision 40690c774567859027ab01f0b3510e6b4bb0a151 passed 246/246 tests on both Python 3.10 and 3.13 (run 45538438545, jobs 138950723890 and 138950724206). Subsequent documentation-only head requires its own CI. See docs/SCOUT_SCENARIO_STORE.md.
- Prior schedule head b85102da70bd46880992e17d361a0ade92750a34 passed Python 3.10/3.13 CI 45537359686; 231 tests observed in Python 3.13 log. Test-first scenario run 45538333181 expected missing module; implementation e6cd0e2712c9645cbaaeb892c3a2db01ac4b8e6c passed 243 tests in Python 3.13 job 138950626099. Additional tests 40690c774567859027ab01f0b3510e6b4bb0a151; draft PR #36. Main acceptance 0/42.
- Next: native scenario editor/list, independent evidence per assumption, conservative review ranking, restart-safe halt and recovery, branch consolidation and independent QA. No new paid service or dependency.


## Native Scout scenario workspace candidate
- R06/E33/E35: Plan scenario window from Scout history; explicit blank-as-unknown financial and scheduling fields, saved immutable plans, exact-context list/load, fresh assessment and UTC-stamped unverified model summary. Every store operation reloads the declared profile and current archive and checks halt state. No external authority or network. Seven regression methods; test-first commit 4585c314e9eb2ba2cc145faf5ec2e19f8d18412e failed as expected (run 45538950556, missing module). Implementation 37cdbd81dd3e8a44f161e249a374bf7d9a51b533; desktop integration 963c470f913bd1ab40e9e8ed44e56c2c60425c67.
- E38/E40: integrated head f10d04bf7d1672256788a3f1f780e20fd36f76bd passed 253/253 on both Python 3.10 and 3.13 (45539097374); Windows source unit, self-test and populated GUI smoke passed (45539097289), packaging canceled after follow-up commit 71c51b169480cd71ef2b3e2e0f64e5585d616921 improved deferred selection-event behavior and checks output after Tk event processing. Replacement exact-head Windows build and frozen smoke pending. Prior scenario baseline passed exact-head CI 45538520497 (246 tests). Draft PR #37. See docs/SCOUT_DESKTOP_SCENARIOS.md.
- Main formal acceptance remains 0/42; no release, evidence verification, live commercial operations, new dependencies or paid provisioning. Next: evidence-weighted ranking, evidence per assumption, durable halt and interrupted-task recovery; consolidate and review the complete desktop candidate. UI actions currently use bounded synchronous local archive calls; performance and independent review remain pending.


## Bounded Scout review ranking candidate
- R06/E13/E14/E22/E33/E35: single-snapshot bounded ranking of current exact-context scenarios, source/capability holds before economics, latest-plan selection without optimistic cherry-picking, ties/future plans unresolved, explicit unknowns, exact exposure and collection-time ordering. Fifteen new regression methods; code/test revision 51330e1207a9d19cea9812b6a9d5664842a83034 passed 268/268 on both Python 3.10 and 3.13 (run 45540850932; jobs 138958712546 and 138958712839). Documentation-only successors require exact-head CI. See docs/SCOUT_REVIEW_RANKING.md; draft PR #38.
- Prior native workspace head e8da3635a04ba466fe7e4227758b1a610a3cd05f passed 253 tests (45539178897), Windows source and frozen GUI smoke plus artifact upload (45539178809, artifact 14988731479). Ranking test-first run 45540775218 expected missing module; implementation 785c01e44bccc8687893773c74405acc8e0ba8f7; additional tests 51330e1207a9d19cea9812b6a9d5664842a83034. Main acceptance 0/42.
- Next: desktop ranking view, independent per-assumption evidence and Council review, restart-safe halt and interrupted-task recovery, performance testing and branch consolidation. No new dependency, paid infrastructure or external authority.


## Native ranked Scout Matrix candidate
- R06/E33/E35: native ranking window accessible from Scout history and desktop; bounded snapshot with explicit source/query/display filters, truncation and UTC counts, preserved tier order, exact modeled USD, conservative collection-time display, reason codes, and exact-context local planning/To Do navigation. Profile reload/revision and halt rechecks, filter invalidation and halt-observed snapshot clearing. No factual verification or execution authority.
- E38: eight new regression methods; test-first run 45541245249 expected missing module. Controller revision 5cffc5ec61492d383f06aa3dc21458515b3136e2 passed 276/276 on both Python 3.10 and 3.13 (45541324514, jobs 138960277686 and 138960278017). Desktop integration d5ff254f2c1c393404a49b33f9d0aebefb1aa30a; Windows workflow db9c4a62b5a4c04f52692a0a805446b6ed196538. Exact integrated/frozen checks pending at entry. See docs/SCOUT_RANKING_MATRIX.md; draft PR #39.
- Prior ranking head d9aab09933b4429c7e6cf22920e418b43d1ab6a2 passed 268 tests (45540933057); prior verified Windows preview e8da3635a04ba466fe7e4227758b1a610a3cd05f (45539178809, artifact 14988731479). Main formal acceptance 0/42; no new paid services, dependencies, external authority or merge. Next: durable halt/recovery, independent scenario evidence and Council coordination, performance and consolidated release review.


## Durable Governor startup and interrupted-task recovery candidate
- E17/E31/E34: every cooperating local desktop session starts halted, persists startup/halt/shutdown and explicit local-ready revision, acquires exclusive OS file lock, reconciles all queued/running events atomically as terminal interrupted (not success), and never replays work. Explicit Resume offline only after recovery, no active task or persistence fault. Halt before disk persistence; guard results, archive and export. No external authorization.
- E38: eleven new regression methods; test-first 45541969325 observed missing module. Guard revision d856a48e8556409ea2d8406f25a1401ceb105913 passed 287/287 on both Python 3.10 and 3.13 (45542070034, jobs 138962722386 and 138962722149), including actual separate-process crash/exclusion, failure rollback and clock checks. Desktop integration f71b17574c114bcfababc1592702ad691c53d7f1; exact integrated/Windows frozen checks pending at entry. See docs/DURABLE_RUNTIME_GUARD.md; draft PR #40.
- Prior Matrix head ad6d77b63905b3dc8edc34117f3424073d67adcd passed 276 tests (45541425046), Windows source/frozen smoke and upload (45541425024, artifact 14990100547). Formal main acceptance 0/42. Local cooperating process only, not older binaries or remote filesystem; cancellation cannot undo completed local writes or already-dispatched GET. No new paid resources/dependencies. Next: per-assumption independent evidence, Council review, stress/independent release review, consolidation.


## Aegis scenario assumption evidence candidate
- E14/E18/E22/E27/E31: bind local file fingerprints to exact immutable saved plan, assumption field and canonical value digest. Seventeen assumption fields; unknown values cannot receive value-bound references. Bounded immutable associations, same-byte replay, explicit byte comparison, before/after archive context and halt checks, no stored file paths/contents or byte-match verdict. Reference coverage is not factual verification; all authority and independent verification flags remain false.
- E38: fifteen new regression methods. Test-first 29bd007c51bd127ff430ae2e0cf192e0d1c8d65e (45542838875) failed as expected for missing module; implementation e74fc39a6ba03ef8535ad2d235275ef80e2a5d93 passed 299 tests in Python 3.13 job 138965506016 (45542919698). Expanded regression revision 62adc46d234c557bceba551055fc2433d81c6b7c passed 302/302 tests on both Python 3.10 and 3.13 (45542947169, jobs 138965597124 and 138965596793). Documentation-only successors require exact-head CI. See docs/SCENARIO_ASSUMPTION_EVIDENCE.md; draft PR #41.
- Previous Governor exact head ddd813014d91fee6ba2055d6064de86481fba322 passed 287 tests (45542186371), Windows source and frozen GUI smoke plus artifact upload (45542186400, artifact 14988869680). Main formal acceptance 0/42. No dependency adoption, paid infrastructure, raw evidence data or external authority. Next: native per-assumption evidence editor, Council criterion-based independent verification, bounded delegation and integrated release review. File-byte match alone cannot authenticate content, issuer or commercial terms.


## Native Aegis assumption evidence workspace candidate
- E14/E18/E22/E27/E35: saved-plan-only evidence window, all 17 canonical assumptions and unknowns, scoped immutable local references, explicit attachment and byte recheck, visible reference coverage distinct from factual verification. Current profile/context and halt rechecks, no persisted raw file data or verdict. Eight new regression methods and populated GUI attach/reload/match/mismatch smoke.
- E38: test-first 173674a5f38057ed67ae2e822ff5d6a88889faa8 (45543585916) failed as expected for missing module; controller 9596d8ae3502f4f39861f40ea08af5febfd7fc16 passed 310 tests in Python 3.13 (45543669550, job 138968003359). Scenario integration 0ed5e834c44a3572392be68dc3eeba28e6e818e1; Windows workflow 63f943d94d3d4ee4fc498f761c13f7aa5445f1d6. Exact integrated/frozen checks pending at entry. See docs/AEGIS_EVIDENCE_WORKSPACE.md; draft PR #42.
- Prior Aegis exact head 730a6762d751c10ef22c1627a92acff96a4d0bd5 passed 302 tests (45543009854); prior Governor Windows preview ddd813014d91fee6ba2055d6064de86481fba322 verified (45542186400, artifact 14988869680). Main formal acceptance 0/42. No new paid resources, runtime dependencies or external authority. Next: independent criterion-based Council review and bounded handoffs, performance/security and consolidated release review.


## Durable Council attempt ledger candidate
- E15/E31: separate local trusted-coordinator ledger, immutable task contract digest, reserve before dispatch, atomic sequential attempts 1–3, single outstanding reservation, idempotent exact completion and explicit interrupted-reservation recovery without replay. Third unsuccessful/interrupted attempt escalates; terminal tasks cannot reset via registration. No raw artifact/agent text stored; no reviewer, fact, release or external authority implied.
- E38: fifteen new regression methods, including two concurrent connections racing reservation, restart and terminal escalation, corrupt state, transaction rollback and halt controls. Test-first e9578cfd7be98230de3a8c11c3ab9e2a251b286d (45544130172) failed as expected for missing module; implementation 66ba0c4f29a050d646fa54371fd6e3a97ea64a11; expanded tests 5c0ac87166257bc1a5a233b85e6c5c5cb4a0a7ee. Expanded code/test head 5c0ac87166257bc1a5a233b85e6c5c5cb4a0a7ee passed 325/325 tests on Python 3.10 and 3.13 (45544243659, jobs 138969884289 and 138969884658). Subsequent documentation-only head requires exact-head CI. See docs/COUNCIL_DURABLE_ATTEMPTS.md; draft PR #44.
- Prior Aegis UI head 20d177090d35c5fabb969fa580012c164ac78cff passed unit CI 45543746235 and source/frozen Windows GUI and artifact upload 45543746266 (artifact 14990835831). PR #43 is an independently active sibling criterion evaluator; its observed head d0967bc3da977bc51bcccba4a76e199cf9670ad6 failed malformed Unicode digest test (45543915317). No modification or dependency on that unverified head. Next: integrate verified criterion checks with ledger via trusted coordinator/RuntimeGuard and stable task allocation, independent review, stress and consolidated release. Main formal acceptance 0/42. No new dependencies, paid infrastructure, live actions or merge.


## Guarded Council criterion/attempt integration candidate
- E14/E15/E16/E31: isolated draft PR #45 on verified ledger baseline 47e922769f5b6233a79235d50f2d5d929db96b82. Preserve fourteen pinned PR #43 tests; narrowly correct canonical ASCII digest validation before compare_digest (244fef4c68e700526c5bbca58c971252aef021c0). Original sibling branch unchanged at d0967bc3da977bc51bcccba4a76e199cf9670ad6, failed run 45543915317; no merge.
- Trusted coordinator cae6f9e76bdc2aa59ec6ef49136bc46d6290dbb1 derives stable task identity from a trusted scope digest, pins policy/criterion contract, requires explicit registration, reserves before local checks, records canonical review digest, enforces one attempt per call and durable escalation after three. Missing artifacts consume an attempt; malformed inputs rejected before reserve. Interrupted attempts remain reserved until trusted worker-drained recovery. No agent-provided verdict or authority.
- E38: 12 new coordinator tests plus 14 retained sibling tests. Test-first run 45545595227 expected missing modules. First integrated revision passed 349/349 on both Python versions (45545685803). Additional tests 068ca31a10b862dede5fc096d8566d81ddf6ba8d intentionally exposed two report-boundary gaps (45545737240); hardened revision af34de4ecc2cb08fba2ff4fb322029033b5f57a4 passed **351/351** on Python 3.10 and 3.13 (45545786994, jobs 138974954034 and 138974953621). Strict report schema and independent recomputation of exact snapshot digests prevent a mismatched report being recorded. Documentation-only head CI tracked separately. See docs/COUNCIL_GUARDED_COORDINATOR.md.
- Main formal acceptance remains 0/42. Latest verified Windows preview still Aegis UI head 20d177090d35c5fabb969fa580012c164ac78cff (45543746266, artifact 14990835831). No new dependency, paid infrastructure, actual external action or release claim. Next: trusted local scope/predicate registry, RuntimeGuard-bound exclusive recovery, scenario-specific Council review and consolidated release review; no authenticated independent reviewer or live autonomous execution yet.


## Scenario-bound local Council policy candidate
- E13/E14/E15/E22/E31: fixed trusted five-criterion local research policy (source/capability, financial fit, delivery schedule, collection timing, reference coverage) bound to an exact saved scenario, current declared profile and coherent archive snapshot. Stable plan-derived task ID and immutable plan integrity pins; adding references or changing evaluation time does not reset retry limits. Inspect without reserving, explicitly register, then invoke one guarded review attempt. Stale/blocked sources and incompatible models veto local fit; unresolved inputs/references remain unresolved. No factual verification, raw file reading or external authority.
- E38: 15 new tests. Test-first e437b8ff59cbd07ef913aaae43afc589f663697c (45546286953) failed as expected for missing module. Implementation fdff88969448a1bff84b854927c49c93a3fc0379 passed 363/363 on both Python versions (45546379087). Expanded code/test head b72e0035781e86327a742ef0a0296749ae58df0b passed **366/366** on Python 3.10 and 3.13 (45546413719, jobs 138977005491 and 138977005947), including post-commit profile drift withholding and classification veto. Documentation-only successor checks tracked separately. Draft PR #46; see docs/SCENARIO_COUNCIL_POLICY.md.
- Prior guarded coordinator exact head 42a7e1dff7275094bdc9b916d040aca38702aae7 verified 351 tests (45545857657). Latest verified Windows preview remains Aegis UI head 20d177090d35c5fabb969fa580012c164ac78cff (45543746266, artifact 14990835831), not this Council adapter. Main formal acceptance 0/42. No new dependencies, paid infrastructure or external actions. Full dynamic snapshot is returned but not persisted atomically with ledger report digest. Next: durable full-snapshot audit, RuntimeGuard-bound recovery and native Council review, independent factual/issuer verification and consolidation toward release. No authenticated reviewer or autonomous worker claimed.


## Durable Council review audit candidate
- E18/E19/E31/E34: retain the complete structured local scenario snapshot and criterion review atomically with Council attempt completion in the existing SQLite ledger. Version 2 attempt record links to bounded immutable audit by SHA-256; validate identity, report digest, policy, reference IDs, model fingerprints, canonical context and reason codes on retrieval. Legacy digest-only records and interrupted reservations remain explicitly labeled; no historical result grants current authority. Audit rollback leaves reserved attempt consumed. No raw document content, filesystem paths or credentials retained.
- E38: test-first 8890fd7d19dce803254f36bb48b057b87ce6ca74 (45546866700) failed as expected for missing module. Schema 2251dece5bbf66f6222eb29a4f3cb4a5a1bd52cf, atomic ledger 9b5ce37ea65eaf6d5032276ac3f19c30ad5038aa, coordinator ff0b34deb01f44ac1cb95698c185152bc599284f, integrated adapter 7522eb2129bdadb5e5e053fc3586c9500d2ca5b0 passed 378/378 on both Python 3.10 and 3.13 (45547018238, jobs 138978964585 and 138978964238). Expanded tests e911da367e3d83eecfb5de9ca2c01f2863ad4263 add legacy upgrade, exact replay and orphan detection, for 15 new methods total; expanded code/test head e911da367e3d83eecfb5de9ca2c01f2863ad4263 passed 381/381 on both Python 3.10 and 3.13 (45547118260, jobs 138979298106 and 138979297866). Documentation-only successor CI tracked separately. Draft PR #47; docs/COUNCIL_DURABLE_AUDIT.md.
- Prior scenario Council head 50efa4628127952d851749d705202d7f9b4974aa passed CI 45546491474. Main acceptance 0/42; older binaries cannot read v2 task records. No new dependency, paid infrastructure, Windows package or live commercial actions. Next: RuntimeGuard-bound interrupted Council recovery, native Council review and historical audit dashboard, integrated release review. Local hashes do not authenticate reviewers or establish commercial facts.


## Governor-bound Council recovery candidate
- E17/E31/E34: existing exclusive RuntimeGuard ownership reconciles all outstanding Council reservations on halted startup, atomically across the Council ledger. Third interrupted attempt escalates; earlier audits and completed tasks preserved. Explicit same-session halted recovery requires owning thread, drained worker and no reentrant Council action; resume rejects outstanding reservations. Fixed local saved-plan actions are owner-thread gated, and failed review with outstanding reservation asserts halt. No external action permission or replay.
- E38: 12 initial tests at ff224c4a7c6cd3f9eeb06ba942fdea819aed53de reproduced missing behavior in 45547852497. Ledger maintenance fc470465a3a972f68dbdd789bc3cdc2fa5c88c67 and runtime integration 8a93a69b57b8cc23da952bfa04cc447f8a956bfb (45547961733 both unit jobs passed); desktop recovery control and populated smoke at 998481d201dc396793e65cf60db8102064274d5a passed 393/393 on both Python 3.10 and 3.13 (45547992818 jobs 138982106748 and 138982107022). Expanded code/test head 46ef0db4cdf888606c83a70cbe18b4f70d34eee8 passed 396/396 on Python 3.10 and 3.13 (45548045184 jobs 138982269264 and 138982269693), total 15 new methods. Subsequent documentation/workflow head checks tracked separately. Draft PR #48. See docs/COUNCIL_RUNTIME_RECOVERY.md.
- E40: prior Aegis Windows preview remains verified at 20d177090d35c5fabb969fa580012c164ac78cff (45543746266, artifact 14990835831). New preview checks required before claiming updated package. Main acceptance 0/42. Local cooperative ownership and bounded synchronous scans, not authenticated multi-tenant security. Existing direct library callers require trusted boundary; no independent factual verification, new dependencies, paid infrastructure or live actions. Next: native Council review/history controls routed through RuntimeGuard with worker-future exclusion, then consolidated security/release review.


## Native Council review and audit dashboard candidate
- E13/E15/E34: native fixed-saved-plan Council workspace with explicit local inspection, registration, one review attempt and separate historical audit selection. All operations route through desktop worker-future exclusion and RuntimeGuard owner-thread facade. No implicit review or replay; halt/busy clears displayed data. Model and evidence coverage are explicitly unverified; legacy, reserved and interrupted records never fabricate snapshots. Available from scenario editor including Ranked Matrix navigation.
- E38/E40: prior runtime exact head 4b774c390b3c240440f30c233eb4ad628fbe0e98 passed Linux unit CI 45548137421 but Windows run 45548137356 failed in test cleanup (WinError 32 on still-open SQLite fixture connection; no artifact). Narrow fixture fix 1af1fb1e2b6974d9c0eb754a3748b1bdadd88fb4 uses contextlib.closing and retains transaction commit. Test-first e29fb06c123c64bae161c130cbd506729981b26b (45549039466) observed expected missing module. Workspace 1408a0041c6a7817fad2ca3d7fcbf70cce8430e3 passed 406/406 on both Python 3.10 and 3.13 (45549125623, jobs 138985784985 and 138985785320), ten new methods. Scenario integration 28eb365ae54d2aaadf98c31cd3feabdc1baddfbe, Matrix c6be3b971ad12a25e05ae871d2b28d481c27599e and desktop 13b7e93aa8995ed332eaab03253db58c855d7861. Exact integrated and Windows source/frozen checks tracked separately. Draft PR #49; see docs/COUNCIL_NATIVE_DASHBOARD.md.
- Main formal acceptance remains 0/42. Latest verified prior executable Aegis head 20d177090d35c5fabb969fa580012c164ac78cff (45543746266, artifact 14990835831). No independent factual verification, new runtime dependency, paid infrastructure, live commercial actions or merge. Next: integrated review/packaging, approval-gated Operator drafts, performance/security checks and consolidation. Older application versions cannot read upgraded v2 Council records.


## Operator draft-only quotation request candidate
- E24/E25/E31: standalone deterministic RFQ preparation/rendering, declared scenario/observation/profile and supplier scope, 1–16 explicit USD line items, bounded immutable draft persistence and explicit local acknowledgment of the exact saved identity. No verified recipient, dispatch, legal commitment, payment, or current decision. Archive/profile revalidation, trusted runtime and native Operator workspace remain pending.
- E38: eleven targeted tests passed privately on Python 3.13 after expected missing-module failure (full checkout unavailable due to container DNS; relevant Governor definitions copied from exact base); implementation and tests verified by Git blob hash before one combined commit. Remote full-suite verification pending at entry. Avoid intentional failing CI submissions in response to user email-noise concern. See docs/OPERATOR_DRAFT_RFQ.md.
- E40: native Council head 64ea24dbfd6eea97d074165b809b1f9a0243f856 verified 406 tests (45549230868), Windows source/frozen GUI and artifact upload (45549230908, artifact 14991894500). Previous Windows cleanup defect corrected. Main formal acceptance 0/42. No new dependencies, paid infrastructure, release merge or commercial actions. Next: archive-bound Operator drafting/recipient qualification, desktop integration and consolidated release review.


## Operator archive and supplier scope candidate
- E24/E25/E31: RFQ v2 resolves the exact saved Scout plan/current profile/observation using local Council inspection; source holds deny drafting. Normalized Atlas supplier declaration must cover explicit item classifications/region, USD, supplier role and freshness; immutable supplier fingerprint binds draft and local acknowledgment. Legacy v1 remains historical; new scoped acknowledgment requires v2. RuntimeGuard fixed owner-thread draft facade, halt/worker/reentry checks, no recipient or live action. No capacity, buyer or price verification claimed.
- E38: previous Operator exact head 17f52f1af7e9e4480edb37ada85bbbea6b20fb1d verified 417/417 on Python 3.10 and 3.13 (45549734210). Eleven new focused tests and four full integration tests; 22/22 targeted local tests passed with mocked archive/Atlas boundaries, full repository checkout unavailable due to DNS. Single combined commit, no intentional remote red. Exact head cd632660bc4500fe0db8aecbee8a246c93ff813c passed 432/432 on Python 3.10 and 3.13 (45550294917, jobs 138989611223 and 138989611155). See docs/OPERATOR_SCENARIO_SCOPE.md.
- E40: latest verified Council Windows head 64ea24dbfd6eea97d074165b809b1f9a0243f856 (45549230908, artifact 14991894500). No new Windows package, paid infrastructure, external authority or main merge; main 0/42. Next native Operator workspace and recipient/correspondence verification, consolidation and independent release review.


## Native Operator RFQ workspace candidate
- E24/E25/E34/E40: fixed saved-plan native quotation composer with explicit declared supplier fields and 1–16 item lines, separate preview/save/acknowledge and historical list. RuntimeGuard and desktop worker-future checks cover all actions. History is bounded to 100 rows, validated per returned record, with truncation disclosure. No recipient or send operation; acknowledgment revalidates exact declaration and plan. Existing-only draft database reads reject missing schema rather than replacing history. No raw supplier declaration persisted.
- E38: ten new focused workspace/listing tests plus one hosted real-runtime history test. Expected missing-module failure observed privately; 32/32 focused tests passed on local Python 3.13 using exact previous Operator modules, minimal Governor local policy and mocked archive/Atlas/desktop boundaries. Private Xvfb Tk smoke passed using real DraftStore and mocked archive/supplier validation. Exact source/test blobs verified before publishing. One combined commit; no deliberately failing remote submissions. Hosted full suite and actual Windows/frozen GUI fixture checks pending at entry; record final results in PR rather than extra CI-triggering documentation commits. See docs/OPERATOR_NATIVE_WORKSPACE.md.
- E40: verified prior Council preview 64ea24dbfd6eea97d074165b809b1f9a0243f856 (45549230908, artifact 14991894500). Main 0/42, no new dependency, paid infrastructure, live actions or merge. Next recipient qualification/evidence and draft correspondence, Genesis/Catalyst comparison and consolidated release review.


## E25 recipient declaration and correspondence preview candidate
- Reviewed latest 21:01 hourly sprint notes and verified native Operator baseline 6c4c1249d0e85c874ec86af95628dbfa31491f7d (443 tests, Windows 45550842222 artifact 14994355367); superseded PR #53 closed. E25: exact saved RFQ/supplier-bound role-contact declaration, same-domain source consistency, owner-selected Aegis fingerprint, expected-preview-ID confirmation, immutable bounded historical recipient records, fixed RuntimeGuard local operations and nonbinding correspondence renderer. No mailbox control, factual identity, contact permission or execution verification. See docs/OPERATOR_RECIPIENT_EVIDENCE.md.
- Ten new regression methods (eight focused and two real-runtime integration). Full private checkout unavailable due to DNS; coherent atomic remote submission, hosted suite pending. Backend only; no new Windows GUI build claimed, no paid dependency, live action or main merge. Formal main acceptance 0/42. Next: native recipient review UI, local thread/response model, authentic source/recipient verification, integrated release review.


## Seven-repository adoption and bounded agent context
- See docs/AGENT_ENGINEERING_ADOPTION.md H01–H08 mapped to E01–E42. Pinned Browser Use, Mem0, Scientific Agent Skills, Diagram Design, community Anthropic Cybersecurity Skills, Awesome Harness Engineering and OpenViking; inspected license metadata and relevant files. No upstream code, scripts or runtime packages installed. Browser Use Python >=3.11, Mem0 provider/telemetry dependencies, OpenViking AGPL, harness README license uncertainty defer adoption pending review.
- H01/E13/E14/E18/E27/E34/E38: deterministic scoped summary/review/evidence packet, exact validated local Council snapshot, fixed byte budgets, explicit omissions, reason/evidence ID projection, same-snapshot expansion and native Council context controls. Eight focused and one existing real-runtime test; populated Windows GUI smoke extends previous verification. Coherent atomic commit; private clone blocked by DNS; CI pending at entry.
- H02 browser isolation, H03 scoped memory, H04 scientific evaluation, H05 local diagrams, H06 defensive hardening, H07 verified harness/release, H08 commercial Operator thread/delivery milestones queued in that document. Latest baseline PR #54 head 0583b40bb7abe9dacefdf86f1040cf1438b987f2: 453 tests passed (45552714855). Prior verified Windows artifact 14994355367 (45550842222). Main acceptance 0/42. No new paid resources, live actions, commercial commitments, or modifications to Nexus Operative.


## H08/E25 — durable local correspondence candidate
- Base PR #83 head `6aa69c2d54ae0ed9f6458a947dd6502b1d8f72d3`: [706 tests and Python CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45568681788), [Windows source/frozen and Genesis CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45568682000) passed.
- E25/E18/E31: fixed exact saved draft/recipient scope, one bounded persistent local history per pair, transactional compare-and-append, no reset/replay, expected evidence fingerprint on confirmed local append, backup allowlist inclusion. Four new regression/integration tests; candidate CI pending. E25 remains partial: no native thread UI, authenticated contact, consent, real delivery or independent reply proof.
- E19/E40: separate local database included in closed-instance backup inventory; restore drill with thread history remains outstanding. E16/E17: trusted runtime idle/halt/scope boundary retained; no new external action. Cross-store post-commit checks are not distributed transactions.
- Reuse audit: Operative journal blob 59ee08e7734347897b29af33603dffba783ec9ad, read-only; agency-agents MIT handoff template at 8ae6164602c95ca78828b148b9052460ee426885, metadata/evidence/continuity ideas only. No source copied or dependencies added. Main accepted gates remain 0/42.

## H08/H07 — correspondence recovery diagnostic candidate
- Exact #84 baseline `b96293ecd79889b0eb27cdc7ed032415da2774cb`: [Python 3.10 and 3.13 CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45572369228) passed; Python 3.13 log reports 710 tests. [Windows source, GUI, Genesis and packaged verification](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45572369204) passed. Formal main acceptance remains 0/42.
- E25/E18/E19/E31/E38/E40: expand the existing owned Genesis lifecycle to exercise a scoped RFQ, declared role mailbox, evidence-fingerprinted simulated response, stale-head and wrong-recipient rejection, all three correspondence databases in the backup, evidence-file exclusion, explicit resume, historical identity equality and expired-source refusal after restoration. Extend deterministic report assertions. Candidate CI pending; local checkout DNS unavailable. No raw evidence files restored, no authentic contact, real reply, delivery or authorization claimed. Native recipient/thread UI remains next.
- Reuse review: Operative journal blob 59ee08e7734347897b29af33603dffba783ec9ad; agency-agents pinned 8ae6164602c95ca78828b148b9052460ee426885 handoff template and both adaptation PRs inspected read-only. No imported source, dependencies or paid services.

## H08 — native correspondence candidate
- E25/E34/E38/E40: scoped native recipient preview/save and historical thread inspection/open, explicit local confirmation, halt display clearing and synthetic GUI smoke. Four controller tests. Base #85 CI and Windows passed; candidate CI pending. See docs/OPERATOR_NATIVE_CORRESPONDENCE.md. Main accepted gates 0/42. Next: event append UI and independent release review.

## H08 — native local correspondence event candidate
- E25/E27/E34/E38/E40: #86 exact head 9bf86d2dbc7d35a2c83ac1c531d79828c4e7da98 passed both Python CI jobs (714 tests observed on Python 3.13, [CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45590817326)) and [Windows preview](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45590817688). New native event preview and explicit compare-and-append use the existing RuntimeGuard, bind exact thread/head/kind/evidence, verify returned append and readback, and clear transient state on changes/halt. Three new controller tests and expanded owned GUI smoke. Full checkout DNS blocked; candidate verification pending. No delivery, authenticated reply, or generated follow-up text; local follow-up document reference only. Main formal gates remain 0/42. Next: generated nonbinding follow-up text and integrated acceptance review.

## H08 — deterministic local follow-up preview candidate
- E25/E27/E34/E38/E40: base #87 exact head `ab2847414cc0c3e38b86cb391655e5b0647f9c27` passed [Python 3.10/3.13 CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45600396303) (717 tests observed in Python 3.13) and [Windows source/GUI/frozen verification](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45600396264). New native preview requires an intact local thread and a simulated reply, binds exact recipient/draft/thread/head and latest reply event/evidence fingerprint, composes fixed nonbinding clarification prose without reading raw evidence, refuses a follow-up already recorded after that reply, and respects halt/busy clearing. Four new controller tests and expanded GUI smoke. No automatic persistence or transmission; historical preview is not a fresh authorization. Candidate CI pending; local checkout DNS blocked. Main accepted gates remain 0/42.
- Read-only reuse review: Operative journal blob 59ee08e7734347897b29af33603dffba783ec9ad; agency-agents MIT pinned 8ae6164602c95ca78828b148b9052460ee426885 handoff template. Exact contextual identity and no inferred authority; no copied code or new dependencies. Next: explicit reviewed local export/registration, integrated acceptance review.

## H08/H07 — explicit local follow-up export and consolidated candidate
- Base #88 exact head `a67cbcefe26561c4080e74c4033c33f88d855ce1`: [Python CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45610843466) passed both jobs; Python 3.13 log reports 721 tests. [Windows source/frozen checks](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45610843456) passed, artifact 15020365877.
- E25/E27/E31/E34: explicit local export revalidates reviewed thread, writes a new bounded UTF-8 text file with exact provenance, checks actual fingerprint, then prepares a distinct local event confirmation; no automatic append, delivery or overwrite. Partial/unregistered file may remain after interruption; do not delete or retry automatically. Local owner filesystem trust remains required; no mapped-drive or OS sandbox guarantee.
- E38: three isolated helper tests passed privately after expected missing-module error; full checkout DNS unavailable. Two new controller tests and expanded owned GUI smoke require hosted verification. E39/E40/E42: consolidate latest descendant on a main-targeting draft without merging or changing old PRs; main remains 0/42. See RELEASE_REVIEW.md. No new dependencies, paid services, live actions or Operative modifications.


## RC2 scoped Scout-to-Operator requirements review candidate (2026-11-25)
- Prior RC2 #89 `426517d2ece7b9b73827e2c2d0685af079412bdc`: both Python versions passed 726 tests in run 45620248029; Windows run 45620247946 succeeded (artifact 15022864857).
- E13/E14/E21/E25/E27/E31/E38, H08: exact current archive/profile scoped declared service review, source holds take precedence over structural fit; no title inference or authority. Five new actual workspace regressions. See docs/SCOUT_SCOPED_SERVICE_REVIEW.md. Full local checkout DNS blocked; exact-head hosted checks pending. No new packages or live actions. No formal main gate promotion; 0/42.

## RC2 native Scout service requirements form (2026-11-25)
- Predecessor `8f9a147c11c7dae3a9bfa1dc7331baac17963abc`: both Python logs 731 tests passed, run 45630193966; Windows run 45630193991 succeeded, artifact 15029614617.
- E13/E14/E21/E25/E27/E33/E34/E38, H04/H05/H08: native read-only explicit requirements form bound to selected archive context, no inferred values or external authority. Six private focused parser tests passed; exact blobs matched; integrated GUI smoke expanded, hosted CI pending. See docs/SCOUT_NATIVE_REQUIREMENTS_FORM.md. Formal main gate acceptance unchanged 0/42. No new dependencies, costs, live actions or Operative modifications.

## RC2 guarded Scout-to-Operator work sample (2026-11-25)
- Prior exact head `b602208d7c3b6b671cd6eef1936962f9d81b856d`: both Python jobs 737 tests passed (45630948209); Windows source/frozen checks passed (45630948208, artifact 15032035028).
- E13/E14/E16/E17/E21/E27/E28/E31/E32/E38, H04/H08: exact stable review scope, current saved-plan revalidation, actual declared input sizes/fingerprints and parsed cell bound, four service routes through existing guarded deterministic producer, post-production scope recheck, no file export/registration or external authority. Six private focused tests passed; four real integration cases added; hosted exact-head verification pending. See docs/SCOUT_GUARDED_SAMPLE.md. Main formal acceptance remains 0/42. No paid provisioning, new dependencies or Operative changes.

## RC2 native exact-scope work sample preview (2026-11-25)
- Predecessor `c8579e87302aa720935dd188ff6f595765fb83b9`: both Python jobs 747 tests passed (45631691800); Windows 45631706441 source/GUI passed, packaging pending at implementation preflight.
- E13/E14/E16/E17/E21/E27/E31/E32/E33/E34/E38/E40, H04/H05/H08: native exact-plan local file preview with explicit confirmation, pre-read source/route/plan checks, bounded stable file reads and existing guarded QA/revalidation. Three new focused tests passed (nine isolated total); three real integrated tests and native positive/held smoke expanded; exact-head hosted verification pending. See docs/SCOUT_NATIVE_SCOPED_SAMPLE.md. No export/registration/authority; no formal gate promotion (0/42), paid services, dependencies or Operative changes.

## RC2 exact-scope local export candidate (2026-11-25)
- Predecessor `83aec0c0860002de38f0cde3efeec79704d29b2b`: 753 tests passed both Python versions (45632410219); Windows 45632409983 pending at initial inspection.
- E16/E17/E21/E27/E31/E32/E33/E34/E38/E40: separate confirmed local export, exact source/plan/requirement revalidation, contract/report/artifact pin comparison, no-overwrite file publication and one-shot native preview consumption. Four focused private tests passed; three integrated regression methods and native owned smoke added; hosted verification pending. See docs/SCOUT_SCOPED_EXPORT.md. Durable registration still requires separate provenance integration; formal main gate acceptance 0/42. No paid resources, external action, dependencies or Operative changes.

## RC2 scoped durable obligation provenance candidate (2026-11-25)
- Predecessor `bca3f5eaf53a847093ffd135d7c7254eb07f3392`: 760 tests passed on both Python versions (45632930377); Windows 45632930222 succeeded (artifact 15030898159).
- E18/E19/E21/E27/E28/E30/E31/E32/E34/E38, H03/H08: freshly scoped sample and actual selected artifact revalidation, complete bounded historical review in existing immutable obligation registration digest, stable legacy obligation identity/no duplicates, history display and simulated invoice scope continuity. Five focused private tests passed; four integrated regression cases added; exact-head hosted checks pending. See docs/SCOUT_SCOPED_OBLIGATION.md. Native registration control and dedicated scoped recovery test pending. Main formal acceptance 0/42; no external action, dependencies, paid resources or Operative changes.

## RC2 complete diagnostic and build-pin verification (2026-11-25)
- Exact predecessor `8004193d28071b172489f7e6508e70d32e93efbd` passed Python 3.10/3.13 ([45635505020](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45635505020), 772 tests) and [Windows source/frozen/Genesis](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45635525043) (772 tests in Windows log; artifact 15032887793, actual PR checkout fedb13cf0f77af8b9478fabb295fb5edc06fb186).
- H07/H08, E25/E31/E32/E37/E38/E39/E40: preview verification now requires all 37 ordered owned diagnostic checks, including correspondence scope/replay/recovery, all 15 identity digests, exactly one simulated correspondence event, a bounded positive restored database count, and distinct thread/head identities. CI explicitly pins attempt and event in addition to commit/tree/run. Optional CLI flags `--attempt 1 --event pull_request` permit independent comparison against the CI log. Three additional negative-control test methods. Older artifacts remain evidence of their own revision, not current acceptance.
- Local full checkout DNS failed; local red/green not executed. Coherent atomic code/tests/docs submission; exact new CI pending. No external authority, signatures, authentication, paid resources, new dependencies, or formal main acceptance (0/42).

## Scout receipt evidence resolution — 2026-11-25
- E06/E18/E31/E38, H03/H06: v2 completed-search receipts retain exact bounded local archive references. Read-time projection validation rejects missing or inconsistent referenced rows; legacy receipts remain explicitly unverified, no backfill or authority promotion. Four new regression methods; no new dependencies or provider calls. See docs/SCOUT_SEARCH_HISTORY.md.
- Base PR #91 exact head 73cb588aaf26e04bdbeb5a12640b94f33ecc68b8: PR CI 45650359317 successful on Python 3.10/3.13; 790 tests observed in 3.13 logs. Windows preview 45650359330 completed successfully (source, GUI, fixture, Genesis and frozen executable checks; artifact 15041145263). Candidate hosted checks pending; full local checkout blocked by DNS. Formal main acceptance remains 0/42; independent review still absent.
- Reuse: rechecked pinned agency-agents handoff templates (8ae6164602c95ca78828b148b9052460ee426885, MIT) and Operative journal blob 59ee08e7734347897b29af33603dffba783ec9ad for bounded evidence references and local audit patterns. No code copied, no upstream dependency or runtime authority added. Next: native receipt-to-observation navigation and source freshness review, then consolidated acceptance.

## Scout exact receipt review — 2026-11-25
- E06/E12/E18/E31/E33/E38, H03/H06: exact selected receipt and historical references checked in one read snapshot; same-source/key drift, age and deadline holds, native numbered review. Five regression methods; see docs/SCOUT_RECEIPT_REVIEW.md. Candidate hosted checks pending; local full checkout DNS blocked.
- Verified predecessor #93 `419264effb08be84c61238a486a5eeb808663e5e`: both Python versions 801 tests passed ([45651419167](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45651419167)); [Windows preview](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45651419257) passed; artifact 15041705807. No provider calls, new dependencies, paid services, authority or formal main acceptance (0/42). Next: consolidate verified stack into a main-targeting release review, independently audit provider permissions, role authorization and release evidence.


## RC3 consolidation and exact receipt native acceptance — 2026-11-25

Predecessor #94 `ed5903a66bfaefa7627bcb04029f3d0bb55957cc`:
[Python CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45652000536)
passed 806 tests on both Python 3.10 and 3.13, including all five exact
receipt regression methods. Its [Windows CI](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45652000623)
passed source unit, source GUI, source fixture-process, source Genesis and
source security steps; packaging was in progress when this increment was
prepared. The earlier #93 Windows artifact 15041705807 is fully verified
for that revision only. The RC2 main-targeting draft #89 and stacked Scout
review branches remain available for independent review.

E06/E12/E18/E31/E33/E38/E39/E40, H03/H06/H07:
the owned desktop smoke now creates a receipt referencing the already
archived synthetic observation with the exact reviewed SAM query, checks
no duplicate observation is inserted, exercises the native historical
receipt review controller and rejects an out-of-range selection. The
nonblocking synthetic selector exists only in the smoke invocation;
normal UI uses the numbered owner dialog. Receipt/history controls occupy
a separate row. Source and frozen GUI smoke must pass for the consolidated
candidate. No provider calls, new dependencies, live authority or
financial commitments. Full local checkout failed with GitHub DNS
resolution; local red/green and independent QA not performed. No formal
main acceptance (0/42).


## RC3 security evidence binding — 2026-11-25

Verified #95 predecessor e2abf03adb7127c3da46595fd745ecb12b2ec33b:
both Python 3.10 and 3.13 logs report 806 tests OK
(45652532839); full Windows source, native receipt GUI, fixture process,
Genesis, security and frozen executable verification succeeded (45652532806,
artifact 15041332928). Development checks authorized by owner; independent
release approval is separate.

E02/E37/E38/E39/E40, H06/H07: bind both existing security review reports to
a v2 preview manifest by exact file SHA-256, byte count and internal report
digest. Strict canonical bounded schemas, pinned distributions, no findings,
false authority flags. Existing v1 bundles remain verifiable as legacy
only. CI explicitly requires v2 with --require-security-reports on write
and verify; v1 cannot meet that policy. No signature, independent
attestation, full SBOM, advisory/license clearance or authentication.
Five isolated helper tests passed locally after expected missing-module
failure (matching blob hashes); four integration tests added; exact full
checkout DNS blocked and hosted candidate checks pending. No new runtime
dependencies, external actions, cost, Operative changes or formal main
acceptance (0/42).

## Awesome resource library — 2026-11-25
- E01/E02/E03/E37/E38, H01-H08: initial targeted survey of GitHub's Awesome topic and related catalogues, 19 exact pinned references, source/blob evidence, license hints and prioritized research steps. All are REFERENCE_ONLY; no upstream code, model, prompt, package, tool or dependency installed. See [resource library](../resources/awesome/README.md) and [adoption plan](../resources/awesome/ADOPTION.md).
- Local standard-library catalogue CLI supports deterministic workstream/category filtering, strict bounded reference validation and rejects automatic install, execution and authority claims. Five isolated local tests passed after expected missing-module red; tested source and test blob hashes matched. Repository catalogue integration test awaits hosted verification. Full git checkout failed DNS; no full local suite or independent acceptance claimed. No provider calls, spend or changes to Operative. Formal main acceptance 0/42.
- Exact RC3 base 80ac719f617f4c594212968d545aca12e320683e: both Python jobs passed 828 tests (45674383337); Windows 45674383449 was still running at preflight. Separate review branch preserves that build and avoids interfering with hourly development. Next: independently audit selected security tooling, then mock and benchmark a bounded local inference worker.

## Local advisory protocol foundation — 2026-11-25
- E13–E16/E27/E37/E38, H01/H04/H06/H07: reference-only local advisory request/response contract, built from the existing exact validated Council evidence projection. Explicit trusted consent, fail-closed Governor state, SHA-256 model/request/snapshot pins, five-minute validity, 64 KiB request and 16 KiB response limits, caller-supplied attempt 1–3, strict bounded JSON output with no arbitrary commands, fabricated evidence, approval, or source-hold removal. Unresolved fields remain visible even if omitted from advice.
- Five isolated Python 3.13 response parser tests passed after expected missing-module import failure; exact tested code and test blobs matched. Four real Council snapshot integration tests await hosted verification. Full local Git checkout failed DNS. No durable advisory retry counter, IPC, model execution, OS containment, UI dispatch, cloud fallback, or independent review is implemented. Request/response digests are associations, not authentication.
- Prior resource-library PR #104 head 4e6b0551c424ba7b54d27de96f1e7fe46ee00a83 passed both Python jobs (834 tests each; 45675295438). Windows 45675295364 was in progress at preflight; preserve that run on its own branch. No new packages, providers, cost, external commercial actions, or changes to Nexus Operative. Formal main acceptance 0/42.
- Next: verified private worker lifecycle with synthetic process-death/timeout/halt fixtures, durable reservations and strict retry accounting, before benchmarking or selecting any model. Continue separate defensive dependency and licensing review.


## Durable local advisory attempt ledger — 2026-11-25

- E15/E16/E18/E19/E31/E37/E38/E40; H03/H06/H07. New standalone AdvisoryAttemptStore uses transactional SQLite reservations, canonical bounded digest-checked records and a maximum three attempts per validated plan ID across model or snapshot changes. A successfully validated response terminates that plan's advisory budget; the third failed or interrupted attempt escalates. No reservation replay, automatic retry, reset, model execution or action authority.
- Explicit Governor consent for reserve/complete/fail; exact current request and snapshot validation on completion; caller must confirm worker drain, and halted recovery requires exclusive ownership and drained workers. These are trusted coordinator assertions, not OS-level proof. The desktop RuntimeGuard does not yet wire this ledger into startup or dispatch. No automatic replay after backup/restore. The closed-instance database backup allowlist now includes local-advisory.sqlite3; only digests, fixed failure codes and timestamps are stored, never raw model output or credentials.
- Seven isolated Python 3.13 SQLite tests passed after expected missing-module failure, using actual storage/transactions, the Exchange Governor policy and mocked advisory request/response boundary. Exact local code/test blob hashes verified. Three real Council/backup integration methods added; full repository checkout DNS blocked, so hosted CI remains required. No independent review claimed.
- Parent PR #105 at 5d929b1d2c718c5340179702cd0b36070e18e36e passed both Python jobs (843 tests each; 45676020671). Windows 45676020523 still running at preflight. Preserve parent build; isolated review branch. Prior #104 Windows 45675295364 passed. No paid services, new dependencies, provider/model calls, commercial actions or changes to Operative. Formal main acceptance 0/42.
- Next: RuntimeGuard owner-thread facade, actual drain/recovery ownership, synthetic isolated worker timeout/process-death checks and bounded IPC; then separately verified local inference benchmark and dependency/license review.


## Runtime-owned advisory recovery — 2026-11-25

- E15/E16/E17/E18/E19/E31/E37/E38/E40, H03/H06/H07: bounded all-plan advisory ledger reconciliation in one transaction, preserving completed states and consuming interrupted reservations; third interruption escalates. Corruption, future timestamps, capacity or a later write failure abort the batch. RuntimeGuard acquires its existing directory lock, starts halted, reconciles optional advisory ledger, reports counts, refuses resume while reservations remain, and requires halted owner-thread idle recovery. Missing ledger is not created. Desktop Settings exposes the separate recovery control and owned GUI smoke tests halt/recovery/resume using an actual saved Council snapshot; no model or dispatch.
- Three focused batch tests failed locally on the absent methods, then all ten isolated ledger tests passed in Python 3.13. Exact local ledger/test Git blob IDs matched. Five actual RuntimeGuard integration tests and native GUI smoke submitted for hosted verification. Full checkout DNS resolution failed; full local regression not performed. This is a cooperating local ownership boundary; future worker integration must prove process death and exclude its supervisor before recovery. Separate event, Council and advisory database recovery operations are not a distributed transaction. Independent review outstanding.
- Exact parent #106 eafabd9680b29b3dbb4bdd844c9eeef7239c5640: both Python 3.10 and 3.13 passed 853 tests (45676932177); Windows 45676932072 passed, artifact 15052078485. Separate UI PR #107 is based on RC3; preserve it and reconcile desktop edits during consolidation. No formal main acceptance (0/42), dependencies, model calls, provider calls, live commercial actions, paid resources or Operative changes.
- Next: fixed synthetic worker contract, actual child cleanup/timeout/death/halt, owner-thread supervision, exact scope revalidation independent of inspection timestamp, then approved runtime/model benchmarking.


## Owned advisory process fixture — 2026-11-25

- E15/E16/E17/E27/E37/E38/E40, H01/H06/H07: a fixed deterministic spawned Python child accepts an exact synthetic advisory request, returns bounded bytes in shared memory, exits before parent validation and is joined/terminated/killed as required. Deadline, unknown halt, nonzero exit, empty/oversized/forged output all fail closed. Explicit consent and existing Council request reconstruction apply at the public fixture boundary; no public target/command/model choice, no raw response returned by public wrapper. This is process separation and cooperative cleanup, not OS containment. The fixture is not a real model and does not consume a durable plan attempt.
- Six focused tests run locally against real spawned children on Python 3.13.5, including teardown checks for leaked children; exact local source/test Git blob IDs verified. Three actual Council integration tests plus owned source/frozen GUI smoke submitted for hosted CI. Full local clone fails DNS; no full local regression or independent QA claimed. Parent #108 exact 5dcf6450aaa7d3c93dfe4e46839e5d2daeb5848b passed 861 tests on Python 3.10/3.13 (45680763014); Windows 45680762786 active at preflight. Preserve separate UI PR #107 and ongoing build.
- No new packages, model calls, provider calls, paid services, actual commercial actions, or Operative changes. Formal main acceptance 0/42. Next: integrate the supervised synthetic worker with owner-thread runtime lifecycle and durable attempt reservations, re-inspect stable current scope independently of timestamp, then benchmark a separately approved locally licensed model under real containment. No automatic retries, cloud fallback, or tool authority.
