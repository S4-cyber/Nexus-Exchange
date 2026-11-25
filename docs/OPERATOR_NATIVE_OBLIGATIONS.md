# Native historical obligation management (H08/R08/E28/E31/E32/E38/E40)

Base: PR #67, 5a39e0d344e004b43594272770b7e3e6aa93de00. Corrected
expiry fixture typo; both Python jobs on 45561107463 passed.
Windows preview 45561113928 was pending at preflight. The previous Windows
native-preview failure was diagnosed and corrected in the base; no new
verified executable claim until exact-head Windows checks finish.

## Candidate

- Native CSV workspace adds explicit registration of a matching existing CSV
  after current preview. Export still consumes preview; registration requires
  a new explicit preview. Registration consumes preview as well, even on
  failure; no implicit database write on export. Existing backend regenerates
  source bytes and validates current plan before actual artifact fingerprint.
- Fixed saved-plan historical ledger window, bounded refresh, explicit inspect,
  exact selected record and expected head, owner-confirmed acceptance/revision/
  rejection claim evidence notes. File selection and fingerprints only, no
  source document interpretation. Never enable buyer approval, invoicing,
  payment, revenue, legal commitment or commercial dispatch. No stored paths.
- Desktop routes only fixed history/list/note calls to RuntimeGuard; existing
  owner/idle/halt checks remain. UI validates canonical registration identity,
  QA binding, note chain, all-false flags and current selection. Clears display
  on edit, selection drift, halt/busy polling, failed refresh or stale head.
  No automatic retry. Historical notes do not imply current lead eligibility.
- Eight regression methods on real saved scenario, exported artifact and
  guard; registration confirmation, stale note head, scope/authority/digest
  tampering, duplicate rows, defensive copies and halt. Source/frozen Windows
  GUI smoke adds actual local register/list/inspect/note/reopen on owned fixture.
  No provider calls, payment, expenses or local test run claimed.

Next: explicitly hypothetical invoice and partial/duplicate/overpayment
reconciliation, then native view and integrated release review. No accepted
main release gate; formal acceptance remains 0/42. PR #60 preserved separately.
