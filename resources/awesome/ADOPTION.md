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
