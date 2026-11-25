# Local advisory contract — implementation candidate

The standard-library module nexus_exchange/local_advisory.py implements a
closed data contract for a future local model. This is not an inference
engine, model installer, sandbox, or live agent runtime.

A trusted caller explicitly approves local advisory construction and
provides the current validated Council snapshot and a selected model
digest. The module invokes the existing Governor's local research policy,
builds the exact evidence context packet, and projects only fixed assumption
field identifiers, known states and bounded reference digests. The request
contains the source hold and exact snapshot/packet pins. It does not include
the raw source material, arbitrary instructions, financial amounts or
credentials. A requested model digest is not proof of the actual loaded
weights.

Requests are bounded to 64 KiB, responses to 16 KiB; the snapshot and
request must both be no more than five minutes old. The caller-supplied
attempt number must be 1–3; this is a schema limit, not a durable retry
enforcement mechanism. The response contains only format, request digest,
model digest and an ordered list of field/reason/reference ID items.
Unknown fields, conflicting states, duplicate items or JSON members,
fabricated or cross-field references, authority flags and commands are
rejected. The validator reconstructs the exact request from the current
trusted snapshot. A review output preserves all unresolved fields and the
source hold, regardless of omitted suggestions, and sets all authority
and independent-verification flags false.

This first stage is deliberately not wired to model calls, a GUI, network
transport, or automated task execution. Hashes are local consistency and
association checks, not signatures. Freshness depends on a trusted clock
and a genuinely current snapshot supplied by the caller. Model authenticity,
IPC isolation, hard deadlines, process termination, durable reservation/
retry accounting, model licensing, hardware benchmarks and independent QA
remain necessary. No model may override the deterministic Council,
Governor, explicit source consent or commercial approval.

Tests: five isolated response-parser tests and four hosted integration
methods exercising actual Council projection, stale context, hold,
consent, halt, attempt cap and resealed mutation. Prior upstream references
remain those pinned in resources/awesome/catalog.json and
docs/AGENT_ENGINEERING_ADOPTION.md. No upstream source copied, package
installed, network endpoint called or cost incurred.
