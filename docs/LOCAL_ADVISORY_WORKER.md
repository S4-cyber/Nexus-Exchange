# Synthetic local advisory worker

This candidate exercises a real spawned child but does not run AI, install
model weights, access networks, or dispatch tools. The built-in child only
echoes fixed field states and existing reference IDs. The fixture digest
identifies the built-in synthetic protocol, not model weights.

Public entry run_advisory_fixture accepts only a trusted Council snapshot,
explicit consent, and a live halt reader. It reconstructs the exact bounded
request using the existing Governor and Council advisory contract. The
private supervisor uses spawn, a fixed worker, at most 64 KiB request bytes
and a 16 KiB response slot. It polls a monotonic deadline (12 seconds default,
15 seconds ceiling), the child must exit normally, and the parent validates
the response, rechecks halt and freshness, and strips raw response bytes
from the public result. In failure it attempts termination then kill and
joins the child; a cleanup failure is never reported as success. Private
failure-injection targets exist for owned tests only.

The standalone diagnostic is not linked to the persistent plan-attempt
ledger or a production UI control. The owned GUI smoke invokes it on a
synthetic saved-plan snapshot and the same smoke runs in the frozen build.
The existing RuntimeGuard recovery implementation remains unchanged; do not
activate an inference worker until its owner-thread supervisor excludes
active work and proves drain/cleanup. Independent current-scope validation
must compare trusted fields separately from inspection timestamps before
recording a completed durable reservation.

Limitations: process separation is not an operating-system sandbox;
the child inherits its process environment and user privileges. No real
untrusted model, downloaded code, plug-in, remote endpoints, arbitrary
tool, credentials or sensitive user data are permitted. The fixed child
does not use these capabilities. Actual OS least privilege, memory budgets,
network/credential isolation, model identity and licensing, and independent
review must be addressed before actual inference. No new dependencies.

Verification: six local focused process tests (Python 3.13.5), three new
Council integration methods, source and frozen GUI smoke awaiting hosted
checks. No full local checkout. All external authority flags false.


## Fixed transcript and cleanup prerequisite

The fixture supervisor now independently checks the entire canonical reply
rather than merely permitting the general advisory schema's valid subset.
Omitted fields, reordered rows, alternate reference IDs and noncanonical
encoding fail the diagnostic. Cleanup attempts kill after a terminate/join
error if the child is still alive, requires a confirmed exit code for a
started child, and emits WORKER_CLEANUP_FAILED for uncertain cleanup.
Five focused test methods passed locally; full regression remains pending
for this increment. A future runtime owner must treat that reason as a
fault, not as a drained failure eligible for recovery. No OS-level crash
containment or persistent dispatch is implemented.
