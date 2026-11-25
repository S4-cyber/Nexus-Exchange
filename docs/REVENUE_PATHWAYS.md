# Scout revenue pathways

Owner requirement: generate potential earned revenue without a mandatory initial deposit, or choose a funded operating route. Both must remain part of the same Scout pipeline.

## Genesis (default, zero cash)
Discover digitally deliverable services, subcontract work, permitted task marketplaces, quote requests and other lawful earned-income opportunities. Prefer existing tools/resources and payment on accepted deliverables. Require evidence that all pre-payment cash exposure is zero, including platform fees, software, supplies, subcontracting, taxes or deposits due before receipt. Unknown costs block zero-capital qualification. Labor/time and nonfinancial obligations remain. No revenue promise.

## Catalyst (optional funded planning)
Owner sets cash budget; modeled exposure cannot exceed it. Future deposit/withdrawal via regulated business bank/payment provider, explicit authentication, verified available balance, transaction caps, approval-bound spending and audited reconciliation. No third-party custody. Budget fields are hypothetical, not bank balances, available funds or payment authorization. Do not provision accounts or incur costs without approval.

## Source hierarchy
1. SAM.gov public opportunities (https://sam.gov/opportunities), official API specification https://open.gsa.gov/api/get-opportunities-public-api/. Public search can be used without an account; automated API needs user API key, date filters, pagination and provider quota. Never expose API keys in logs/links. Distinguish actual solicitations from awards, sources-sought and other non-executable notices. Direct prime awards require appropriate active entity registration (https://sam.gov/entity-registration).
2. SBA SUBNet (https://legacy.sba.gov/federal-contracting/contracting-guide/prime-subcontracting/subcontracting-opportunities): subcontract opportunities; verify prime contractor, terms, restrictions and capabilities. Source-specific authorized collection pending.
3. Grants.gov (https://www.grants.gov/): restricted eligible funding pathway separate from commercial revenue; no assumption that a grant is free operating capital or profit (https://grants.gov/learn-grants/grant-eligibility).
4. Later: vetted private digital-service marketplaces, government/state procurement and permitted paid task sources. Check current platform terms and AI/automation rights before enabling connector. No fake profiles, mass proposals, spam, CAPTCHA bypass or automated attestations.

Current desktop opens only fixed official URLs via explicit user click in default browser. Embedded Windows browser candidate: Edge WebView2 (https://learn.microsoft.com/en-us/microsoft-edge/webview2/), with isolated profiles, origin allowlist, restricted downloads and no privileged bridge into untrusted pages. Actual runtime adapter, user consent, API key storage and authorized read-only network gate are pending.

## Verification and owner To Do
For each lead: verify official source, issuer, active status/deadline, account/entity eligibility, actual delivery capability, allowed AI/subcontracting, written compensation/acceptance/payment timeline, complete cash costs, and exact action authorization. Validate identifiers and cross-check evidence against primary sources. Rule-based validation first; model research only as advisory. Never turn self-declared evidence or checkbox completion into independent verification. Task state must eventually bind to a specific lead, evidence digest, owner profile and scoped authorization; expiry/revocation and exact approval needed for consequential actions. Owner handles login/MFA, identity verification, truthful representations, tax/payment onboarding and required signatures in secure provider flow. Never ask for credentials in chat or put private profiles in GitHub.

No federal contingent-fee brokerage by default. Check applicability of FAR 52.203-5 (https://www.acquisition.gov/far/52.203-5), exceptions and solicitation-specific limitations on subcontracting; do not assume a commission for winning a federal contract is lawful. Prefer actual contracted deliverables, fixed fees for legitimate services and separately reviewed private arrangements. No regulated work without required authorization/licensing.

## Acceptance subgates (mapped to existing 42, no new denominator)
- R01 (E13/E16/E22): zero-capital and funded planning budgets; unknown exposure blocks; no authority from checklist. Candidate implemented.
- R02 (E10/E26/E33): fixed official source links and native pathway/checklist window. Candidate implemented, not an embedded browser.
- R03 (E10–E12): authenticated, read-only SAM adapter with bounded retries, pagination, quotas, redaction, stale and notice-type handling; source-specific fixtures and authorized smoke test.
- R04 (E20/E25/E36): local owner/entity capability profile, secure credential store, provider account verification, least-privilege scopes, consent/revocation.
- R05 (E14/E15/E31): lead-bound persisted checklists, evidence and missing prerequisites; independent evidence verifier, deadline ordering, replay-safe state.
- R06 (E22/E35): rank verified leads by zero cash exposure, expected net return, time to payment, delivery feasibility, risk and deadline; keep grants separate. Unknown evidence blocks execution.
- R07 (E26/E27): isolated WebView2 or equivalent controlled browser; official APIs first. No login bypass or untrusted-page instruction execution.
- R08 (E24–E32): approved draft applications/quotes, owner review and scoped dispatch only where rules allow, deliverable quality checks, mock invoice and reconciliation. No automatic binding commitments.
- R09 (E35/E36/E41): regulated-provider business funding and withdrawal integration, verified balances, owner limits, no custody of third-party funds, signed/reviewed audit.
- R10 (E38–E42): end-to-end zero-cash simulation and funded simulation, verified revenue receipt only after actual acceptance/payment, security/legal review and Windows release.

Next priority: R03 read-only SAM source adapter and R04/R05 profile/evidence tasks before expanding browser autonomy. All live operations remain disabled. No paid provider or account connected in this increment.
