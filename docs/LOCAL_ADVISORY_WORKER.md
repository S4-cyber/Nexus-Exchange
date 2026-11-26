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


## Runtime-owned synthetic reservation candidate (GRI-7)

The headless owner-thread facade reserves an exact saved Council plan before
starting a fixed synthetic supervisor in one executor. While the job is
reserved, all existing owner maintenance and close paths reject concurrent
work. The owner polls, joins the supervisor, re-inspects the saved plan and
atomically completes the original ledger ticket with the fresh scope. Raw
response bytes are not returned. Halt or scope drift withholds the result;
failed jobs leave a reservation for explicit halted recovery, not replay.
Uncertain cleanup faults the current session and blocks resume/recovery.

This is a fixed owned fixture only, not model inference, a GUI control or
OS containment. A process crash/restart cannot yet prove orphan-child cleanup;
existing startup ledger reconciliation is not evidence of OS containment.
Do not enable a real worker before durable quarantine and process-tree
containment, independent QA, and shutdown integration. Full local checkout
remains DNS-blocked; hosted tests are required for this coherent batch.

## Restart-safe launch quarantine candidate (GRI-7)

Before submitting a fixed advisory worker, the owner commits a singleton
reservation ID in the existing event database (autocommit, synchronous FULL).
It clears that marker only after joining its own supervisor and observing a
successful result or an explicitly recognized clean exit. Unknown, launch,
identity and cleanup failures retain the marker. A later owner can inspect
halted status but cannot automatically recover the advisory ledger or resume.
There is deliberately no reset/clear UI or automatic PID-based clearance. A
crash before launch may produce a conservative false-positive hold; do not
delete the marker or database to recover. Review and implement separately
authenticated OS process-tree containment and an evidence-backed recovery path
before a real model or normal production release. This protects cooperating
local sessions, not a hostile administrator or a replaced/restored database.
The fixed synthetic fixture remains the only worker. Four isolated SQLite
marker tests passed locally on Python 3.13; runtime integration and full
regression require hosted verification (local checkout DNS unavailable).

## Desktop shutdown integration candidate (GRI-7 / GRI-10)

The desktop busy predicate includes an owner-held advisory reservation even if
its child has finished. Window close asserts halt, drains the existing Scout
and advisory supervisors, and only then releases local runtime ownership. An
unresolved launch marker is shown as a startup hold; restart is not clearance.
The GUI/frozen smoke now starts a second explicitly approved synthetic attempt
immediately before normal close, reopens the same temporary data directory and
requires exactly one recovered interrupted attempt, no published result, and no
remaining cleanup marker. No new user-facing model launch control or authority.
Full local checkout remains DNS-blocked; these GUI changes require exact-head
hosted Windows verification and independent review.

## Read-only Council budget inspection (GRI-7)

The Council saved-plan window can inspect the synthetic advisory budget without
creating a ledger, reserving an attempt or starting a child. The owner-thread
facade revalidates the selected scenario and applies the idle/halt gate before
returning only state, count and next possible attempt. Missing plan rows are
distinguished from corrupt storage; existing ledger integrity is checked.
The UI rejects invalid state/count transitions and clearly labels historical
metadata as neither current review nor consent. A terminal review cannot be
presented as an available retry. The GUI smoke now checks this read-only path.
Prior exact head 257c273338092ac60f6e162920341f9ec31777d5 passed both
Python jobs (917 tests each, one skipped) and Windows source/frozen smoke:
https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45718814999
and https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45718815057.
New regression awaits hosted CI; local checkout DNS failed. Explicit native
launch consent and OS containment remain separate work, not enabled here.

## Prepared synthetic launch boundary (GRI-7)

Native launch controls must use the owner-thread prepare/start pair rather than
the trusted headless diagnostic entry point. Preparation validates the saved
Council snapshot and bounded fixture request and returns one opaque in-memory
preview identifier, plan and next attempt; no reservation or child is created.
A newer preview, explicit halt, use or runtime restart invalidates it. The
start path requires literal confirmation, exact plan and runtime revision,
fresh scope comparison (five-minute maximum) and the expected attempt inside
the ledger transaction. Scope drift fails closed before reservation. A preview
is not authenticated user identity or permission for any real action. No GUI
launch control, OS isolation or actual model inference is enabled here.

Prior exact head 2f8373b5ca593ec86305442df75a3aeb25557e76 passed 919 tests on both Python versions
(one skipped), source security and Windows packaging:
https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45726115258
https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45726115304.
New full regression requires hosted CI; local GitHub DNS unavailable.


## Native consent and owner polling candidate (GRI-7)

Council prepares an exact saved-plan preview, displays the plan, snapshot and
attempt in a default-No confirmation dialog, and invokes only the prepared-start
facade after literal consent and a second busy/halt check. Declining does not
reserve or consume an attempt. The desktop root polls the owner-held worker
independently of the Council window, disables conflicting controls, and displays
only a completed restricted historical report; halt or failure withholds output.
No model, live dispatch, new dependency or new permission. GUI smoke covers
decline and the native facade shutdown/recovery path. Independent interactive
completion and containment review remain pending.

Prior exact head 5f836cd2f84f6f08b013c988f2eac42c7bd3b8ed passed 922 tests per Python 3.10/3.13 (one skip),
source security and Windows build: https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45732599323
and https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45732599389.
Local clone DNS remains unavailable; new complete regression is hosted only.


## Exact-reservation completion display and native smoke (GRI-7)

The root callback carries its original reservation ticket through polling.
Before rendering a historical completion it checks the plan, terminal attempt,
reservation and request identity, response/model and review digest, and denies
any nonliteral false authority/verification/dispatch flag. This is display
defense in depth, not independent source verification or OS containment.
A separate owned saved plan now exercises normal desktop collection, terminal
budget state, disabled export, re-enabled offline controls, output removal on
halt and explicit resume before the existing interrupted-close regression.
Prior head 285c968fcc9396fa47d89771ad182f84fbed2485 passed 925 tests (one skip) on each Python 3.10/3.13 and Windows source/frozen smoke:
https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45740121846
and https://github.com/S4-cyber/Nexus-Exchange/actions/runs/45740121869.
New code and tests are one batch; local checkout DNS failed, new CI pending.
No model inference, live action or release acceptance.
