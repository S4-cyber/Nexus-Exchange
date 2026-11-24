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
