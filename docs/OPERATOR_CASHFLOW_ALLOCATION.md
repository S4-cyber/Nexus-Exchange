# Cost-adjusted cash flow and allocation sandbox (H08/R08/E29/E30/E32/E35/E38/E40)

Base PR #70 410707aa7e54b528245b93bb49fa130bd1aaa0c6: both Python CI
runs passed (617 tests), Windows preview pending at preflight.
Prior #68 full Windows preview passed. Independent correspondence PR #60 preserved.

## Candidate behavior

- Read-only owner-thread cashflow operation re-resolves exact historical
  invoice, receipt head, current obligation head and immutable saved scenario.
  Validate scenario identity, financial-input fingerprint, compensation and
  payment delay against invoice and obligation. Recheck heads after calculation.
  No mutation, saved allocation, actual balance, transfer or external authority.
- Seven existing owner-declared cost categories: platform fees, software,
  materials, subcontracting, taxes, deposits, other. Exact integer USD cents;
  unknown is null, never zero. Present known subtotal, full cost only if all
  known, full-collection modeled net, as-of received less total costs and
  modeled shortfall. Assume all declared costs reserved from assumed issue;
  before issue, as-of net is unresolved because expense dates are unknown.
  No inference of actual expenses, tax liability or cost recovery.
- Use validated as-of aging, not all-date receipt totals. A hypothetical
  positive surplus allocation requires complete known costs, full as-of
  settlement and unchanged obligation evidence. Otherwise reserve/reinvestment
  amounts are null and hold reasons visible. Explicit reserve basis points
  (0–10000); ceiling reserve to cents; remainder modeled reinvestment.
  No automatic allocation, bank integration, transfers, withdrawal, actual
  revenue, investment advice, portfolio aggregation or spending permission.
  Saved plans are alternatives; do not sum as earned income.
- Native finance workspace includes explicit reserve share and cash-flow
  assessment. Changes to as-of or reserve fields clear prior projection;
  stale scope/halt blocks and requires refresh. UI reconstructs projection
  arithmetic and validates exact hashes/all-false flags, not factual cost
  assumptions. Existing invoice/receipt store unchanged.
- Ten regression methods on actual prior archive/guard/obligation/invoice
  fixtures with known, unknown and loss-making cost assumptions, rounding,
  partial/future receipts, stale evidence/heads, halt and tampering. Source
  and frozen Windows GUI smoke extends to modeled allocation. No local
  test execution claimed; exact-head hosted verification required.

Next: actual Operator capability registry and end-to-end owned Genesis
simulation, then consolidate review stack and independent release review.
Formal main acceptance remains 0/42. No paid services or dependencies.
