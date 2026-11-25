# Integrated offline baseline candidate

Base tested desktop: d4e56a114862736e658eb11640917cae71cb7413, Windows workflow 45528842172 (success, artifact 14983957296). All current application features from the stacked Scout → desktop simulator branch chain are preserved. Independent research and handoff branches are consolidated into one main-targeting candidate without rewriting existing refs.

## Reconciliation decisions
- Retain bounded OpportunityArchive as the sole application opportunity store. Parallel ReviewStore and its isolated tests (head 098f4f9c95296b00f7bd694204b0b67783eafd6b) are intentionally not included because they preserve historical eligibility decisions and are not wired into the desktop. No user database is deleted or migrated.
- Incorporate agent handoff source and tests from 64b1790b1f01c5a69eaf4e65518393bdb0be0e64; reject duplicate evidence references, revalidate handoff fields and bound raw text. Agent claims and evidence strings are not independently verified; ADVANCE is only non-privileged review. Existing unified test workflow replaces separate duplicate handoff CI.
- Include upstream research from ad7cc84a26a35d200cea21fb709b1239260e184c and development protocol from 37c593572a22bcb228fd6747335f7d705597374d, omitting account-specific wallet metadata from the latter. No upstream runtime code/dependencies installed. Existing attribution retained.
- Enable Windows packaging on main and the integration candidate; cancel obsolete builds on the same ref to reduce repeated runner use.
- Preserve individual review branches and PRs for traceability; no main merge or formal gate acceptance assumed.

## Candidate acceptance
Run full unittest suite on Python 3.10/3.13, Windows source and packaged GUI smoke checks, compare exact-head artifacts, independently review source and policy boundaries before promotion. Current previous baseline: 84 passing tests; 7 handoff tests added (including a hardening regression). Expected total 91; actual CI evidence required. No production authorization.

## Unresolved release blockers
Durable halt and process restart recovery; cross-release supersession and source authentication; live read-only provider and complete OCDS validation; verified counterparties and financial assumptions; persistent deal assessments; security/dependency review; installer signing and independent legal/commercial readiness. No additional formal gates accepted yet.
