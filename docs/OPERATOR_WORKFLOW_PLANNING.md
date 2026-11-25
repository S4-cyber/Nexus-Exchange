# Operator: deterministic service workflow decomposition

Base #82 94ae5b73cf6723a07484b0c6fb066aadcaed16ee, 700 tests passed on Python 3.10 and 3.13; Windows
verification was still in progress at preflight.

All four implemented services now have fixed ten-step dependency-ordered
templates: scope, requirements, input pins, validation, production, QA,
owner review, optional export, registration and external hold. Each
template includes concrete service instructions and a content fingerprint.
Scout's existing capability catalog exposes the template identity and
ordered task IDs. No inference from a broad title or new authority.

The immutable workflow plan binds the exact checked service contract,
saved plan, declared inputs (including both hashes/counts when applicable),
template and required QA checks. The native cockpit displays the planned
steps before preview and the exact local QA projection after preview.
Export is optional, registration is a separate confirmed exact-match action.
A successful export response must contain the exact report and all preview
pins; a changed response invalidates progress, without deleting any
already-published file. Input changes and failed actions invalidate live
preview. No arbitrary instructions, tool execution, automatic approvals,
external delivery, or independently verified acceptance. No new database
or dependency. Historical progress is deterministically reconstructed from
the existing validated obligation record; export cannot be inferred from
registration. A recorded action is not proof the owner read the preview.
The progress projection is not an authenticated audit or a proof that
historical source bytes remain available. Six new regression tests and
expanded source/frozen native GUI smoke.
