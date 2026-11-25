# Resource adoption and local agent pathway

Use the catalogue as a curated engineering bibliography, not a list of approved packages. Metadata and selected pinned README/manifest/license excerpts were inspected. Full source, transitive dependency, security, maintenance, model-weight terms, hardware, cost and privacy review remain pending. A CC0 or MIT list does not license all linked projects. A repository's declared license does not establish the license of its dependencies or models. Do not copy content without required notices or permission. Commercial offerings and sponsored links are not endorsements.

## Required evaluation gates

1. Identify a concrete existing E01-E42 or H01-H08 requirement; check whether standard-library code suffices.
2. Resolve the exact upstream release and revision. Verify publisher, source, license and distribution notices, build manifests, dependencies, vulnerabilities and maintenance. Use reviewed tooling, not upstream executable instructions. No network calls or package downloads in automatic registry browsing.
3. In a private isolated environment, use synthetic owned fixtures, minimal permissions, no secrets/customer data, no live providers or unapproved spending. Review data retention, telemetry, model license, source permissions, and transitive costs. Establish reproducible benchmarks.
4. Publish implementation and tests in a coherent isolated PR; verify actual hosted checks, independent QA, and gate evidence. Limit retries to three, then escalate. Never treat an agent verdict or self-reported PASS as release acceptance.
5. Only after separately approved review, adopt the smallest compatible adapter or tool. Preserve Python 3.10 core, offline defaults, no inventory, no custody, no real transactions and no privilege expansion. Do not install every entry or change live settings.

## First work queue

| Sequence | Candidate | Experiment | Acceptance |
|---|---|---|---|
| 1 | Gitleaks, Bandit | Defensive scanning of owned code or synthetic history only, in a separate developer environment | Redacted report; expected synthetic positive and negative controls; no secrets uploaded |
| 2 | pip-audit, Syft, OpenSSF Scorecard | Review build pins and generate distribution inventory; validate actual frozen artifact coverage | Exact versions and artifact pins, explicit advisory and licensing gaps, no false clearance |
| 3 | llama.cpp or Ollama | Benchmark one explicitly licensed, locally selected model on synthetic Council evidence; keep model/provider offline | Exact model digest, hardware memory and latency, bounded input/output, no tool calls or external connections |
| 4 | Pydantic AI and MCP SDK | Evaluate structured outputs and typed tool protocol separately from core; both inspected manifests require Python >=3.11 | Isolated worker compatible with 3.10 core contract; no arbitrary tools, no network grants, independent validation |
| 5 | Public API/dataset lists | Source discovery and fixture review; compare official provider terms | Explicit provenance, bounded read consent, no paid access, no inferred commercial eligibility |

## Local intelligent agent design (proposed, not installed)

A local inference worker may receive an explicitly approved bounded context packet (H01) containing stable evidence references and no credentials or raw personal information. It returns a typed **advisory** response with evidence IDs, uncertainty, and missing-evidence reasons. The current deterministic Council independently validates evidence and the Governor remains the sole action boundary. Enforce fixed model identity, time/token/memory budgets, isolated process, no external network or arbitrary tool execution, no hidden cloud fallback and no new privileges. Limit retries to three and persist redacted outcomes with explicit halt/recovery. The Operator receives only separately reviewed, eligible local tasks. Model output cannot approve transactions, bids, correspondence delivery, signatures, payments, accounts, purchases or source permissions.

Before adding a model worker to the Windows application: design the IPC and allowlist, use a mock provider for malformed outputs, instruction injection, timeout, process death, stale evidence, and halt tests, then independently benchmark and review an exact model and runtime. Neither Ollama nor llama.cpp nor the agent SDKs have been installed or executed by this increment. No hardware specification or model-weight license has been verified. Keep the existing native deterministic functions as fallback; no automatic paid/cloud fallback.

## Resource refresh

At development sprints, search by the current roadmap gap rather than blindly crawling all repositories. Review only new or materially changed references; pin a new revision through a reviewed code change. Never automatically refresh an installed dependency, fetch external prompts, execute repository instructions, or allow a registry entry to modify the Governor. Any future update automation must remain read-only research until separately approved. Existing seven-repository and agency-agents reviews are unchanged.

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
