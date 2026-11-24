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
