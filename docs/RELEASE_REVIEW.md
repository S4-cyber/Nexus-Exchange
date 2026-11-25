# Consolidated offline release review — RC1 candidate

Status: draft, not accepted on main; no production or live commercial authorization.
Base: Genesis PR #73 cac45627635648b5a16611b448eb9d11c2ebf73a
(tree c900b03956cda992925c964201a09c433f22575a); push/PR Python CI
45563193732 and 45563212282 passed 647 tests. Its Windows run
45563212309 was still in progress at preflight. Prior #72 Windows run
45562803758 passed. Main pinned 261a3343de17b537594a333133b9ad118442e6cc.
Base compare: 245 commits ahead, zero behind, 204 changed files. This
candidate targets main directly; it does not merge, close or rewrite earlier PRs.

## Consolidation decisions

- Retain the integrated baseline #21 and the subsequent reviewed stack
  through #73, including the three identical correspondence files from #60.
  Original PRs remain available for independent review and recovery.
- #43 criterion review is incorporated via the later Council coordinator
  stack; current implementation supersedes the earlier candidate. #23's
  standalone offline SAM parser is not included: #24 and subsequent canonical
  SAM connector/archive implement overlapping parsing with a different data
  contract. Do not maintain two incompatible production parsers. A future
  user-selected offline SAM import should reuse the current strict parser.
- Preserve baseline #21's earlier exclusion of disconnected ReviewStore and
  its tests; no user database deletion/migration. This is a review decision,
  not a claim that every historical branch was mechanically merged.
- No paid services, dependencies in the application runtime, provider account
  or Nexus Operative changes. Windows packager remains pinned at PyInstaller
  6.12.0; full transitive build dependency and license review outstanding.

## Candidate gate evidence (not acceptance)

These are scoped evidence indicators from the current integrated source and
observed base CI. "Supported" means relevant local implementation/tests
exist; "Partial" means a material part of the gate remains unfulfilled;
"Blocked" means the required deliverable or external review is unavailable.
They do not change binary acceptance on main. No gate is formally accepted.

| Gate | Candidate evidence | Required remaining review |
|---|---|---|
| E01 | Supported: pinned reuse inventory, SCOUT_FOUNDATION / AGENT_ENGINEERING_ADOPTION | Independent inventory review |
| E02 | Partial: upstream license/manifest notes | Full reuse, runtime/build dependency, distribution license audit |
| E03 | Supported: unittest command and source smoke | Reproduce clean checkout locally |
| E04 | Supported: hosted 3.10/3.13 push/PR CI | Main-targeting exact candidate CI |
| E05 | Supported: strict Scout and source schemas | Independent malformed-input review |
| E06 | Supported: source URL/time and observation digests | Live provenance and attribution audit |
| E07 | Supported: exact identities, archive and duplicate tests | Cross-provider identity reconciliation |
| E08 | Supported: deadline checks, exact USD and FX reference | FX settlement/currency boundary review |
| E09 | Supported: owned procurement fixtures | Fixture coverage review |
| E10 | Partial: bounded consented SAM/TED/UK/Canada adapters | Authorized live sample and provider conformance |
| E11 | Partial: request/page bounds, selected throttles | Provider quotas, continuation, retries and distributed limits |
| E12 | Supported: source failure/stale holds | Real provider failure and current-record compilation |
| E13 | Supported: deterministic Council and ranking | Independent criteria review and calibration |
| E14 | Supported: missing evidence/reason codes | Validate actual facts, not reference counts |
| E15 | Supported: durable bounded attempts, escalation | Independent restart and contention review |
| E16 | Supported: default-deny Governor | Whole-call-site authority audit |
| E17 | Supported: local lock, halt/restart/worker tests | Recovery drill on packaged user environment |
| E18 | Supported: durable SQLite history, scenarios and ledgers | Retention and backup/recovery review |
| E19 | Partial: local integrity and isolation tests | Schema migrations, tenant/access isolation and recovery |
| E20 | Supported: declared Atlas profiles | Authenticated buyer/supplier identity and secure profiles |
| E21 | Partial: declared matching, SEC metadata, capability hints | Independently qualified counterparties and requirements |
| E22 | Supported: modeled costs, probabilities, schedule and returns | Independent commercial assumptions and calculation review |
| E23 | Blocked: catalog/research only | Property adapter, data rights and licensing |
| E24 | Supported: local RFQ drafts | Approved template/content review |
| E25 | Partial: declared recipient evidence and local thread | Persistent correspondence and verified recipient/consent |
| E26 | Partial: bounded supervised owned fixture, not browser | Actual browser containment, egress, origin and process isolation |
| E27 | Partial: bounded CSV/evidence checks | General document extraction, untrusted-content security |
| E28 | Partial: local deliverable obligations | Actual contract templates and independent terms review |
| E29 | Blocked: no signature sandbox | Signature and legal authority verification |
| E30 | Supported: simulated invoice and synthetic receipt reconciliation | Independent financial QA; no real receivables |
| E31 | Supported: idempotency, halt, restart and ledger checks | Interrupted cross-store workflow and backup drill |
| E32 | Supported: owned Genesis diagnostic, 647-test base CI | Exact candidate source/frozen smoke, independent review |
| E33 | Supported: native Scout Matrix | Usability and accessibility review |
| E34 | Supported: native Council and activity views | Owner review and UX/accessibility |
| E35 | Supported: hypothetical receivables, aging and reserve model | No actual balances; independent model review |
| E36 | Blocked: trusted single-user local owner boundary | Authentication, roles and secure credentials |
| E37 | Partial: bounded parsers, negative controls and local hashes | Independent secret, dependency, SBOM and security scan |
| E38 | Partial: failure injections and 647-test base suite | Performance/load benchmarks and adversarial review |
| E39 | Partial: Windows preview and source/frozen smoke | Exact candidate CI/artifact and release environment review |
| E40 | Partial: unsigned portable bundle and recovery tests | Signed installer, repeatable build and real backup/recovery drill |
| E41 | Blocked: commercial/legal review not completed | Independent counsel, data/license and commercial authorization |
| E42 | Blocked: draft only | Accepted gates, independent release review and signed promotion |

Formal main release acceptance remains 0/42; do not turn this table into
a percentage of production readiness. Main merge is a distinct owner/reviewer
decision after verification. E32 is a tested synthetic lifecycle, not revenue.

## Portable Windows preview verification

Use the exact successful Windows workflow linked on the candidate PR.
The workflow checks actual checkout commit and tree (a PR checkout may be
a GitHub synthetic merge commit), then runs all source and packaged smoke
commands. Only after those commands succeed does it generate the manifest
and rerun the isolated source Genesis diagnostic for the report. The
bundle contains NexusExchange.exe, SHA256.txt, GENESIS.json and PREVIEW.json.
Metadata lists completed smoke command names as CI context, not signed
attestations or a cryptographic proof that tests ran.

1. Download the artifact from that run, extract to a new local folder.
2. Compare the hash, not just the filename. PowerShell:
   `(Get-FileHash .\NexusExchange.exe -Algorithm SHA256).Hash` and
   `Get-Content .\SHA256.txt`. Case-insensitive hexadecimal comparison.
3. Inspect PREVIEW.json. Match run ID/attempt and actual checkout commit/tree
   against the workflow log; compare the executable hash. The source diagnostic
   is wholly synthetic. For source users, run
   `python -m nexus_exchange.preview_bundle verify <extracted-directory> --commit <actual-checkout-sha> --tree <checkout-tree-sha> --run-id <run-id>`
   using this candidate's source checkout. The verifier independently checks
   the bundle bytes, canonical metadata, build pins and expected synthetic
   results. No network or user data access. A malicious publisher can
   regenerate hashes; they do not establish authenticity. Do not bypass
   Windows security warnings or install an untrusted executable.
4. Test only in a controlled local preview environment. Do not enter real
   customer data, bank information, payment references or API secrets for a
   release smoke. The source `python desktop.py --genesis-self-test` and
   packaged `NexusExchange.exe --genesis-self-test` exercise a fresh temporary
   directory and discard synthetic working data.

## Recovery / promotion

Use Emergency Halt, let supervised workers drain, then close the app. Do
not copy SQLite files while the app is writing; back up the complete closed
local data directory to an access-controlled location. Restore only into
a separate test environment with compatible schema and verified binary;
startup is halted and requires explicit resume. Verify historical reports
and receipt heads before further testing. No automatic replay or migration
is authorized. A real backup/restore drill, retention policy, installer
signing and independent review remain release blockers. Do not delete
production files or close the historical branches as part of this draft.

Seven new bundle consistency tests; no new application runtime dependency.
Hosted exact-head CI and packaged smoke must be inspected before claims.
No local checkout run claimed.


## Database backup and recovery drill candidate

Use the source CLI `python -m nexus_exchange.database_backup backup <closed-data-dir> <new-backup-dir> --confirm-offline`, `verify <backup-dir>`, then `restore <backup-dir> <new-test-dir> --confirm-offline` with absolute local paths. This is database-only; manually retain original evidence and exported deliverables separately. The implementation requires a clean shutdown and acquires the existing cooperating runtime lock, denies sidecars and unknown database-like names, validates SQLite integrity and known table presence, hashes/copies bounded files, verifies the exact manifest, never overwrites, and restores only into a new directory. Backups are NOT encrypted; store them on access-controlled encrypted storage. No live instance, production restore, user data transfer or automatic resume. A malicious local process or rewritten manifest can defeat local consistency checks. The owned Genesis diagnostic now reopens a restored copy and verifies Council, obligation and receipt history before modeled settlement. This is supporting E18/E19/E31/E37/E40 evidence, not independent acceptance. See docs/DATABASE_BACKUP.md.


## Security inventory candidate

See [SECURITY_INVENTORY.md](SECURITY_INVENTORY.md). The preview workflow now uses an isolated Windows build environment and the exact seven build-package versions observed in successful RC1 CI (including previously installed packaging), verifies dependencies with pip check and emits bounded installed-build and source-tripwire reports. This is not a complete frozen-binary SBOM, hash-locked dependency supply chain, vulnerability scan, history secret scan or license clearance. E02/E37 remain partial; independent security review is still required.

## Consolidation refresh — 2026-11-25

Latest verified ancestor: #88 `a67cbcefe26561c4080e74c4033c33f88d855ce1`, 260 commits ahead of main `261a3343de17b537594a333133b9ad118442e6cc`, zero behind (229 changed paths from compare at preflight). Both Python jobs passed in [45610843466](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45610843466); 721 tests observed in 3.13 log. [Windows](https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45610843456) passed with artifact 15020365877. New consolidated draft includes the local follow-up export increment; earlier review stack and #74 preserved for review. No gate promoted on this evidence alone: E25 remains partial (recipient control/consent unverified), E26/E36/E37/E38/E40/E41 require remaining review. Exact consolidated candidate CI and independent acceptance still required. No external actions or new dependencies. Formal main acceptance 0/42.
