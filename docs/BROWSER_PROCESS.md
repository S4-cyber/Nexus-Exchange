# H02 — supervised owned fixture process (E17/E26/E27/E38/E40)

Base: PR #58, exact head d0093cc04d96334e300647fc400719d5978594fa.
Observed prior push/PR tests and Windows source/frozen GUI preview succeeded
(45556973340, 45556986616, 45556986619).

## Acceptance for this candidate

- Dedicated multiprocessing spawn context, one fixed trusted child, no shell
  commands, arbitrary task, URL, callback, credential or browser profile.
- Parent monotonic deadline including normal launch time, short timed joins,
  cooperative halt checks while supervising, termination then kill fallback
  with bounded join and no success if cleanup fails. No retry/replay.
- Fixed 8 KiB raw shared result slot: no blocking result pipe, no untrusted
  pickle result deserialization. Inspect only after child exits successfully.
- Strict canonical JSON, exact child PID and plan binding, known asset byte
  fingerprints and sizes, result/trace digest validation, bounded elapsed
  fields and all external authority flags false. Child trace is self-reported,
  not independently authenticated. No raw HTML/CSS or error text returned.
- Ten tests, including real spawn, stalled child, halt, bad exit, missing/large
  result, identity/authority/asset tampering and process cleanup. Source and
  frozen Windows process smoke via --fixture-process-self-test; explicit
  freeze_support and expanded PR CI scope. Existing native in-process buttons
  are unchanged until responsive worker/owner-thread integration is reviewed.

## Honest limits

This is a supervised trusted Python child, NOT a real browser, OS sandbox,
network deny mechanism, independent verifier or commercial authority. Spawn
inherits ordinary environment/user permissions. No untrusted code, provider
data, real Chrome profile, network actions or new dependency is authorized.
A process start call itself is not preempted by the deadline; cleanup can add
up to the two bounded joins and OS calls. No process-tree guarantee for
arbitrary external descendants (the fixed child creates none).
No paid infrastructure or commercial activity.

Next: owner-controlled responsive desktop worker with cancellation/drain and
Governor integration, then evaluate pinned browser dependency in an isolated
owned environment with pre-request interception, OS egress containment,
process-tree cleanup and fixture-only routing before real provider pilots.
No main merge or formal gate acceptance (0/42). Hosted exact-head verification
required; no deliberate failing remote intermediate commit.
