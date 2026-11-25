# Operator simulated receivables (H08/R08/E29/E30/E31/E32/E38)

Base PR #68 d13de84bf544165c3cf5d0e85ad2b7eaef4db978: both Python
CI runs passed (596 tests); Windows source GUI and process smoke passed;
packaged candidate status pending at preflight. Corrected prior PR #67
full Windows preview succeeded (45561113928). Parallel #60 preserved.

## Candidate acceptance

- One hypothetical USD invoice for the entire saved scenario compensation,
  pinned to the exact registered obligation, evidence head, contract,
  artifact, QA and canonical saved financial inputs. Latest historical note
  must be an acceptance claim; it is not authenticated or treated as real
  customer approval. Explicit assumed issue/delivery date on/after that note,
  modeled due date from the saved payment delay, positive known amount and
  exact integer cents. No taxes, actual payer or actual invoice issuance.
- Fixed owner-thread preview, confirmed create, historical find/read and
  confirmed synthetic receipt operations through RuntimeGuard. Preview does
  not create storage. Create requires exact preview ID and latest evidence
  head. One simulated invoice per plan/obligation (no double invoicing of
  full plan compensation), exact idempotent repeat. Different saved plans
  are alternative scenarios, not additive portfolio revenue.
- Separate bounded SQLite database, 10,000 invoices and 64 receipts per
  invoice, strict canonical schemas, expected-head chain, monotonic recorded
  time and simulated receipt date, unique synthetic SIM- references across
  all invoices, no partial write on failure. Reject excess, zero, duplicate,
  stale-head or post-settlement receipts. Changes to obligation evidence hold
  further synthetic payments; historical reading remains available. Reopening
  reconstructs received/outstanding cents and unpaid/partial/settled status.
- All real acceptance, actual invoice, receivable, payment, revenue, funds,
  reinvestment and external authority flags remain false. No provider API,
  bank identifier, customer contact, private records or real transactions.
  No aggregate revenue total; alternate plans cannot be added as earned income.
- Eleven regression methods on actual saved scenario/guard/export/obligation
  and isolated storage fixtures; exact sums, stale and duplicate reference,
  drift, integrity, rollback, scope, confirmation, bounds and halt. No new
  paid resource or runtime dependency. Backend only; native finance workspace
  and updated Windows package remain next; no local test execution claimed.

The store trusts the RuntimeGuard as scope admission authority; hashes and
local SQLite are integrity checks, not external signatures, factual evidence
or protection against malicious local database rewrites. Cross-store checks
are not distributed transactions. No credit notes, refunds, fees, tax,
accounting recognition or actual bank reconciliation in this candidate.

Next: native simulated receivables view, as-of aging/expected collection,
cost-adjusted hypothetical cash flow and reinvestment modeling, then
independent review and integrated release consolidation. Formal main gate
acceptance unchanged (0/42).
