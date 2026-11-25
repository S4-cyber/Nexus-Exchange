# Native per-plan simulated finance (H08/R08/E29/E30/E31/E32/E38/E40)

Base PR #69 a0d7681335a4ad1e12df865da0c41d7348e5b63c: both Python push
and PR suites passed (607 tests). Prior #68 Windows full preview passed.

Native finance workspace opens from an explicitly inspected obligation.
Fixed simulation preview, confirmed create, refresh and confirmed synthetic
receipt controls route to existing RuntimeGuard via exact operation names.
No actual invoice, payout, bank details or real payment reference. Revalidate
invoice scope, registration digest, note pin, receipt sequence and exact
integer-cent totals. Another obligation under the same plan cannot relabel a
saved invoice; revised evidence allows historical read but no new receipt.
Backend independently checks current evidence on writes. The window is pinned
to the inspected note chain; reopen from refreshed obligation to update it.
Invalidate preview on issue-date edits, halt/busy or error; clear stale record
on failed payment; explicit refresh required.

As-of model calendar projection independently reconstructs eligible receipts
on/before the date, excludes future-dated receipts, counts no invoice face
before assumed issue, treats the due date as not overdue until the following
calendar day, and calculates overdue amount and elapsed days. Distinguish
all-recorded hypothetical totals from date-specific totals. No aggregation
across alternative plans, cost deductions, tax, actual income, spendable
balance, real settlement, credit notes or reinvestment authorization. All
authority and actual financial flags remain false.

Ten regression methods use the real saved-plan/obligation/receivables
implementation and negative controls; source and frozen Windows GUI smoke
now exercise preview/create, partial receipt, aging, settlement and refresh
with owned synthetic data. No external calls or new dependencies, no local
checkout/test claim. Exact-head CI and Windows results required.

Next: cost-adjusted modeled cash-flow and allocation sandbox with explicit
unknown costs, no cross-scenario double counting, and independent release
consolidation. Formal main gate acceptance unchanged (0/42).
