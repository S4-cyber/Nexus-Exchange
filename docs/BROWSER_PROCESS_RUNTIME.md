# H02 — responsive supervised Scout process (E17/E26/E33/E38/E40)

Base PR #59, exact head db2d5cd8bef65ed3f4048d6f62087a6650e12a57.
Both Python push and PR suites passed; prior PR #58 frozen GUI preview passed.
Parallel H08 correspondence work on PR #60 remains separate; no merge or rewrite.

## Acceptance candidate

- Fixed owner-thread start/poll/drain operations; validate consent and exact
  fixture before launch, idle journal and pending Council reservation checks.
- A dedicated supervisor thread owns the child-process operation. It receives
  only the validated fixed plan and read-only thread-safe halt callback. No
  SQLite, UI or caller-selected executable/callback in the worker.
- Reserve before submit; exclude other desktop worker paths, Council,
  Operator, resume, maintenance and close until owner collection joins the
  supervisor. Poll returns no report until done. Halt suppresses even a
  previously completed but uncollected result. Failure triggers persistent
  halt, no retries; explicit cleanup failure latches runtime fault.
- Desktop controls start the process, schedule nonblocking polling, leave
  Emergency halt usable, clear old exports, display only completed synthetic
  report; normal task entry blocked during reservation. Shutdown first asserts
  halt and drains supervisor before releasing the local runtime lock.
- Ten tests, including real spawned child under owner guard, halt/drain,
  active task, concurrent admission, thread ownership, late result
  suppression and failure. Windows source/frozen GUI tests drive real
  async fixture execution and cancellation; branch/path scope expanded.
- Keep the earlier synchronous fixture facade for regression compatibility;
  native buttons now use the process-backed operation.

## Limitations

Trusted built-in fixture code only, no actual browser, OS-level egress sandbox,
network permission, external authority or paid dependency. No durable
diagnostic journal; reservation is local process state. Shutdown may block on
OS process start/cleanup; cleanup failure is detected and disables resume, not
proof of descendant-tree containment. Tk polling is cooperative and only the
owner changes UI/SQLite. Independent browser sandbox, provider consent and
integration review remain required. Formal main gate acceptance 0/42.
Hosted exact-head CI required; no local checkout/test run claimed.
