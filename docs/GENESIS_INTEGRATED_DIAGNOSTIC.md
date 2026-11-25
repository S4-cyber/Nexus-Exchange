# Owned Genesis lifecycle integration candidate (E10/E13–E18/E21/E22/E24–E32/E35/E38–E40)

Base PR #72: 4b661b19825fb0335bb8c66fca26c6b26c9a106b. Both Python push
and PR tests passed (637 tests). Prior #71 full Windows preview succeeded.
PR #72 Windows packaging pending at preflight.

## Executable diagnostic
Run `python -m nexus_exchange.genesis_diagnostic` for the canonical JSON report,
or `python desktop.py --genesis-self-test` for exit status. Windows packaged
smoke runs the same fixed diagnostic. No user path, credential, callback,
external service or real opportunity is accepted. Fresh temporary directory
and fixed advancing clock; all fixture working files removed before returning.
The real SAM parser receives only one owned fixture page through injected fixed
transport, with active CSV, generic IT and inactive CSV rows. No actual provider
request. Explicitly synthetic titles and references, never inserted in user data.

One real code path: archive/idempotency, capability-first review, saved zero-budget
model, declared requirements structure, Council missing-evidence then review-only
outcome with all 17 synthetic assumption references and no independent verification,
actual CSV byte generation/QA/export, no overwrite, local obligation registration,
unverified acceptance claim, simulated invoice, partial receipt, duplicate and
overpayment rejection, no premature allocation, emergency halt, close/reopen
with explicit resume, historical Council/obligation/receipt reconstruction,
final settlement, as-of future receipt exclusion, hypothetical reserve allocation.
Expected model: USD 0 pre-payment exposure, USD 120 probability-adjusted expected
net, hypothetical USD 200 fully settled, USD 50 reserve and USD 150 reinvestment.
All actual acceptance/payment/authority/funds/zero-capital verification flags false.
No automatic real transactions or inference of guaranteed income. Report carries
content identities and checked stages, not paths or real customer data.

## Parallel work consolidation
Independent PR #60 (02499b277fc0cf08c13505f2198311486204ab32, base
d0093cc04d96334e300647fc400719d5978594fa) passed both Python push/PR CI
(45557310617 and 45557317593). Its three standalone files were absent in
the #72 tree. Transplant those exact files into this isolated candidate:
docs/CORRESPONDENCE_THREAD.md, nexus_exchange/correspondence_thread.py,
tests/test_correspondence_thread.py. The original branch and main are not
changed. Correspondence model is local in-memory chain logic, not persistent
outbox or authenticated communication; its seven tests are included in the
combined suite but not falsely claimed as part of Genesis CSV delivery.

Three new diagnostic tests (complete deterministic run, confirmation denial,
failure cleanup) plus seven correspondence tests. Source/frozen Windows
lifecycle smoke required. No new dependencies, services or spending; local
checkout/test execution not claimed. Integration remains draft pending exact
head CI, Windows smoke, security, acceptance review and main consolidation.
Formal main gates 0/42. Next: review full branch stack and establish a
single integrated release candidate with documented E01–E42 evidence and
remaining actual-source/authorization gaps.
