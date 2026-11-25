# H02 — offline browser fixture contract (E16/E26/E27/E38)

Candidate based on review/agent-context-harness, PR #55.

## Acceptance for this increment

- Only two fixed synthetic fixture IDs; reserved .invalid origin, exact URL and
  media/resource matches. No user/agent URL, live provider or DNS/network access.
- Explicit bounded request and relative elapsed-time fields, strictly typed
  input, ordered first document, optional exact stylesheet, no repeats.
- Reject unknown fields, non-GET requests, redirects, non-200 responses,
  downloads, scripts, cross-fixture resources, encoded/query/userinfo variants,
  malformed inputs, halt and unknown halt.
- Deterministic plan/trace/report fingerprints; canonical plan reconstruction,
  all authority flags false; general Governor FETCH_EXTERNAL remains disabled.
- Tests cover positive and negative controls. No dependency, credential, paid
  API, browser profile, external action or GUI change.

## Trust boundary

This is a pure synthetic completion-trace validator, not a browser, live
network guard, authenticated audit log, or proof of independently observed
events. Its elapsed time is a supplied fixture value, not a real clock.
A matching trace neither proves completeness nor confers any permission.
No provider content is read; no page text or agent instructions are processed.

## Next steps (not accepted)

1. Create an isolated owned fixture renderer/transport with a trusted monotonic
   deadline, pre-request enforcement and request accounting including failures.
2. Validate all top-level navigation, subresources, redirects, DNS/IP egress,
   browser process lifecycle, cleanup and denied form/download/auth actions.
   Post-hoc trace matching alone is insufficient.
3. Integrate the trusted RuntimeGuard and explicit owner research consent before
   considering a read-only provider-specific pilot; review provider terms,
   upstream license, browser dependencies and Python compatibility. Prefer APIs.
4. Review Windows packaging, independent adversarial tests, content quarantine
   and user-visible failure reason codes. No credentials, logged-in browser
   profiles, private pages, submissions or commercial execution by default.

Full local Git checkout blocked by DNS in this development environment. Source,
regression tests and docs submitted atomically; exact-head hosted CI must be
observed before claiming pass. This is partial H02/E26 candidate work, not an
accepted gate; formal main acceptance remains unchanged.
