# Upstream integration register

## OCDS Merge
Source: https://github.com/open-contracting/ocds-merge
Reviewed revision: a75d1f6d5d2dc413c4ca6c83646af41d9e839e9c
Published license: BSD-3-Clause. Verify license at pinned revision before adoption.
Specification: https://standard.open-contracting.org/latest/en/schema/merging/
Decision: evaluate using the upstream compiler rather than implementing incremental release merging ourselves. Existing snapshot selector accepts complete snapshots only. Never feed incremental releases into it as though complete.
Acceptance: pin package and transitive dependencies; verify schema offline; test null deletion, identifier merges, chronology, ties, cancelled tenders and decimal preservation. Preserve source release lineage. No remote schema fetching without authorization.

## Additional candidates
- https://github.com/open-contracting/kingfisher-collect — collection adapters, E10–E12.
- https://github.com/open-contracting/ocdskit — transformation tooling, E05–E09.
- https://github.com/open-contracting/cardinal-rs — risk indicators, E13–E14.
- https://github.com/open-contracting/lib-cove-ocds — data validation, E05.
These are research candidates, not installed dependencies.

## Recurring adoption rule
For each sprint, check for existing relevant implementations before writing new subsystems. Record source revision, license, dependency/security review, integration boundary, regression evidence and disposition. Prefer small adapters, no credential copying, no unapproved network access or spending. Do not claim upstream adoption until tests demonstrate it.
