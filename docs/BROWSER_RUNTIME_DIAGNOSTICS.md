# H02 — native Scout diagnostic and Governor boundary

Base: PR #57 (push and PR CI successful), exact head f6fd1e95ac4c0b3c551c4a3e2901183952f40fee.

## Candidate acceptance (E16/E17/E26/E33/E38/E40)

- RuntimeGuard fixed browser_fixture operation: owner thread, exclusive local
  session, healthy resumed state, idle journal, exact confirmation and known
  fixture. Fixed two-request and five-second budget; no user-supplied URL, plan,
  credentials, clock or dispatch callback.
- Separate active flag prevents reentrant Council/Operator/browser calls,
  recovery, resume or close until diagnostic returns. Pending Council
  reservation halts before access; unexpected execution failure halts.
- Trusted live halt callback checked before/after every local lookup and at
  completion, result withheld on halt. No retry or automatic replay.
- Desktop buttons for both fixtures, disabled at startup/halt/active worker,
  explicit click only, bounded JSON diagnostic displayed in existing output.
  Clear old export state before run and clear output on halt. No raw content,
  provider access or external authority. Results are transient, not commercial
  leads and not durable audit records.
- Ten RuntimeGuard regression methods (including thread ownership,
  reentry, active task, halt during access, fault, pending Council work,
  result suppression and confirmation); Windows source/frozen GUI smoke
  exercises both controls and halt clearing. Windows workflow base/path scope
  explicitly expanded to this PR stack, not disabled or bypassed.

## Limitations and next gates

The browser runner is a synchronous trusted in-memory simulator, not a real
browser sandbox or independent security boundary. The cooperative callback is
not hard preemption; the desktop thread cannot process a new button event
during execution, and no external browser process is launched. No DOM/JS,
network interception, actual provider data, credentials, costs or live action.
A real browser requires isolated process, trusted hard deadline and kill,
all-request interception/egress deny, local fixture server or route fulfillment,
sandbox lifecycle, failure tests, dependency/license review and separate
provider-specific owner consent. Consider a dedicated worker and cancel/drain
handling before any live pilot. Formal main release acceptance remains 0/42.
Hosted test/Windows evidence must be observed for this exact head; no
deliberate red intermediate commits.
