# H02 — owned offline fixture transport (E16/E26/E27/E38)

Base: review/browser-fixture-contract, PR #56 (both push and PR CI successful).

## Implementation and acceptance

- Execute one of two fixed, immutable, in-memory owned HTML/CSS fixture pairs.
  The real entry point uses monotonic_ns, never caller timestamps.
- Validate the canonical prior contract; before every asset lookup enforce
  halt, request budget, deadline, exact GET and exact resource order/scope.
  Count a rejected attempt; close on denial; no retries or partial success.
- Recheck elapsed time after local byte retrieval and at completion. Bound
  bytes and media. A limited HTML parser discovers the single stylesheet
  reference; unknown tags/attributes fail. A discovered link never bypasses
  the transport policy. No arbitrary HTML accepted at the public entry point.
- Verify complete two-resource trace using the previous validator; record
  hashes and sizes, attempt count and relative elapsed time, no raw content.
  Keep every independent verification/external authority flag false.
- Thirteen regression methods: real and deterministic clocks, deadline and
  clock regression, malformed requests, halt between reads, request count,
  closure/replay, response bounds, markup, off-origin link and plan tampering.

## Boundaries

This is an in-process trusted local fixture simulator, not a browser, actual
rendering engine, network interception layer, authenticated log, or security
sandbox for hostile code. The internal clock injection is test-only. No hard
preemption of stalled code, concurrent halt monitoring, external URLs,
provider data, credentials, downloads, scripts, cookies, payments or forms.
The public function receives a snapshot of halt; trusted RuntimeGuard
integration and live pre-request enforcement remain separate acceptance work.
No new dependencies, expenses, or authority.

Next: bind fixed operations to owner-thread RuntimeGuard and a native
diagnostic surface; then evaluate isolated owned browser fixtures with real
process deadline, interception of all resource classes, DNS/IP/redirect
enforcement and cleanup. Do not allow real provider access until reviewed
terms, explicit source-specific consent and independent security tests.

Local git ls-remote was blocked by DNS. Submit source/tests/docs atomically
on isolated review branch; exact-head hosted CI required. Formal main
acceptance unchanged (0/42); this is partial E26 candidate evidence.
