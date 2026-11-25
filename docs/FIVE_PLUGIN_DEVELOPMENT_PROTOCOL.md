# Five-plugin development protocol

Status: proposed development process; review before merging. Updated 2026-11-24.

## Purpose

A repeatable, cost-controlled process for hourly scheduled development and interactive development prompts. Reuse what works, not every tool on every run. The connected ChatGPT plugins are **development-time** tools: installation does not create deployed runtime credentials or automatically link external products to the app.

## Start-of-run preflight (always)

1. Fetch the **exact** target repository and base/development head; inspect open PRs, active work, CI results, the current roadmap and relevant project-specific release instructions.
2. Check for overlapping hourly writes. Work on an isolated review branch. Never rewrite active branches or merge without verified project-specific acceptance.
3. Choose the highest-value, independently verifiable tasks and their tests; batch read-only inspection, parallelize independent work only when safe.
4. Record the exact acceptance criteria before making changes. Use separate developer and reviewer evidence; fail closed on absent evidence.
5. Limit external calls and tokens by benefit; do not interpret maximum utilization as permission to purchase cloud resources or incur metered charges.

## Plugins: invoke by concrete trigger

| Plugin | Activate when | Do not do automatically |
|---|---|---|
| Superpowers | Planning architecture, TDD, regression repair, code review and proof-before-claim verification; read current applicable skill | Skip mandatory tests or treat role prompts as actual execution |
| Coder | User-requested website/app interface planning, explicit prototype/build-link exploration, UI code or code review | Follow affiliate builder links or assume generated previews synchronize with GitHub |
| Vercel | Vercel project is accessible and relevant; read Git deployment, preview build/CI, runtime logs, app traces and deployment protection | Create billable projects/sandboxes or deploy unstable research code merely to invoke plugin |
| TinyFish | A specific authorized public page, browser-only test, or permitted read-only Scout source needs interaction | Spend wallet credits on browser runs, deep research, bulk datasets or automatic monitors absent explicit budget authorization |
| Supabase | An actual selected database project and storage/auth/schema work are needed; inspect existing tables, migration state, RLS/advisories and docs before changes | Provision a project/branch, run migrations on an unknown project, or expose privileged keys |

### Known connection limits to recheck, not permanent assumptions

- Vercel `get_git_deployment_context` returned zero teams to this connection on 2026-11-24. No Vercel project link or preview deployment was established by this protocol.
- Supabase `list_projects` returned no projects on 2026-11-24. No database or migration was created.
- TinyFish browser-agent operations can be metered. No paid run authorized here. Verify available budget before any billable operation.
- Coder may produce an **optional third-party builder link**; it is not an in-repository code integration or hosted Nexus release.

## Engineering and reporting loop

- **Discover**: code, CI, dependencies, vulnerabilities, blockers, current branch and last evidence.
- **Plan**: select independent work, dependencies, acceptance criteria, exact gate IDs and rollback path.
- **Implement**: isolated branch, minimal blast radius, no secrets, no unapproved cloud changes.
- **Verify**: run exact-head unit/integration/security tests, record commands, outcome, tested commit and gaps. Do not claim green CI if only local tests ran.
- **Review**: explicit security/QA assessment, code review; stage preview only with confirmed environment, approval gates and expected costs.
- **Report**: changed files, commit/PR links, observed test evidence, accepted gates and denominator, blocked gates, next tasks, plugins actually used, expenses incurred and required user actions.

## Safety and cost defaults

- No real-money trading, bank movement, live bids, signatures, contracts, purchases or outreach from an agent handoff.
- No inventory custody or third-party fund custody for Exchange; no unapproved financial activation for Operative.
- Never store credentials, broker/account evidence, live counterparty data or customer details in public GitHub repositories.
- Enforce default-deny externally consequential actions, reviewer independence, bounded retries, idempotency, logs and emergency-stop precedence.
- Zero new recurring services or API charges without explicit owner approval. Existing pre-paid TinyFish wallet credit is not an automatic spending authorization.
- Preserve each project's separate CI, readiness gates, security and release permission. No percentage inflation from documentation or agent prompts.

## Subsequent development prompt checklist

Read this document and current roadmap again, then inspect current state; do not rely on old conversation summaries alone. When a plugin is missing or lacks team/project permissions, record a precise blocker and continue offline, reviewable implementation. Never promise background progress outside the explicitly configured hourly automation.

## Nexus Exchange specialization

Primary: Scout sources and provenance, Council reason codes, Governor authorization, persisted opportunity memory, buyer/supplier matching, draft-only Operator and end-to-end simulated deal. Map evidence to E01–E42 in docs/ROADMAP.md, treating the coordination scaffold as supporting research only, not accepted E13–E16. Use the consolidated candidate as the reference after its checks and review.


## Quiet CI submission discipline (user notification concern)
Perform expected-failure tests in a private local environment whenever available. Submit implementation, regression tests and supporting documentation together in one commit on an isolated review branch; do not deliberately submit red or cancellation-generating intermediate commits. If full local checkout is unavailable, document the exact targeted harness or unverified boundary, then run full hosted CI on the coherent change. Never conceal genuine failures, disable required checks, or claim unobserved test results. Record final CI evidence in the PR body rather than triggering repetitive documentation-only builds.
