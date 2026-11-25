# Commercial economics (E22 candidate)

`assess_deal` composes the existing Governor and Atlas. It re-evaluates supplied buyer and supplier profiles and an opportunity at an explicit time, then evaluates one hypothetical fee-only intermediary scenario. It requires the same classification and region requirements as Atlas. No network access, no inventory acquisition, no custody of third-party funds, and no authorization to spend or transact.

Inputs: currency matching the opportunity; nonnegative decimal-text fee_if_collected, upfront_cost, completion_cost and exposure_limit; probabilities of completion and collection conditional on completion as decimal strings between 0 and 1; and explicit assumptions. The fee is independently supplied, never inferred from the tender budget or the parties' declared capacity. Inputs are hypothetical, not verified quotes, payment obligations or forecasts. All relevant modeled costs should include applicable fees and taxes; amounts from different currencies must not be combined.

- Expected fee = fee × probability of completion × probability of collection conditional on completion.
- Expected cost = upfront cost + completion cost × probability of completion.
- Expected net = expected fee − expected cost.
- Net if paid = fee − upfront cost − completion cost.
- Maximum modeled loss = upfront cost + completion cost, even if the probability of completion is zero (conservative scenario bound, not a comprehensive legal liability limit).

Review eligibility requires Atlas compatibility, strictly positive expected net and maximum modeled loss no greater than the explicit exposure limit. This limit is an analysis input, not an authorized spending budget. No result grants commercial authority. Monetary arithmetic uses Python standard-library Decimal with a local precision context, and no new runtime dependencies. The result remains a conditional scenario; actual risks include costs after failed completion, disputes, nonpayment, tax/legal obligations and errors in the assumptions.

Synthetic example: fee 200 USD; upfront 20; completion cost 40; completion probability 0.5; conditional collection probability 0.8; exposure limit 100. Expected fee 80, expected cost 40, expected net 40, net if paid 140 and maximum modeled loss 60 USD. These are synthetic figures, not earnings estimates for Nexus Exchange.

## Reuse and next gates
Reuse Atlas, Scout, and Governor rather than introducing another matching or policy engine. Exact arithmetic follows Python Decimal's context-controlled model (https://docs.python.org/3/library/decimal.html). No upstream code copied. Further steps: desktop scenario import/inspection; provenance and evidence for each financial assumption; sensitivity analysis; verified buyer/supplier linkage; persistent scenario audit; legal and commercial review; independent authorization and spending controls.
