# Council runtime recovery and dispatch (review candidate)

E17/E31/E34/E38/E40. Base ef95f6d1aef7d7f8fb95852a0ac1deb630de752f verified at 45547189235 (381 tests). Local cooperating desktop only.

## Design and acceptance
- Reuse RuntimeGuard's OS-exclusive directory ownership. On startup persist halted state, reconcile the existing event journal, and recover all outstanding Council reservations in the existing Council database before enabling any resume. No Council database is created merely to recover an absent file. Existing unreadable/malformed databases fail closed; no automatic reset.
- Private ledger maintenance performs a bounded all-task validation and atomic batch reconciliation while the runtime remains halted. It does not bypass or expose a public research/dispatch permission. Mark reserved attempts interrupted (third attempt escalates); keep completed reports and existing audit digests unchanged. Any corrupted row, orphaned audit, clock rollback or later write failure aborts the entire Council batch. Event journal and Council ledger remain separate transactions; an earlier event recovery may commit even if Council startup is blocked.
- Explicit same-session recovery requires halted state, runtime owning thread, live exclusive lock and no active Council dispatch or queued/running journal task. Resume refuses remaining reservations. Recovery does not run predicates or replay work and does not clear halt. Desktop invokes this only after its worker future has drained. No caller-supplied ownership flag at the runtime facade.
- Provide fixed owner-thread Council actions (inspect/register/run_once/history) for a saved plan ID; no arbitrary callback, policy, status, path, or automatic dispatch. Block when halted, runtime faulted, closed, reentrant, or journal worker active. Future desktop workspace must route through this facade and respect the desktop worker-future gate. Existing direct store/adapter APIs are trusted local library interfaces, not security isolation against arbitrary local code.
- Test-first ff224c4a7c6cd3f9eeb06ba942fdea819aed53de: real subprocess crash, all-task recovery, third interruption escalation, thread/worker gating, malformed storage, rollback and full scenario review/audit. Verify both Python versions and Windows source/frozen smoke if enabled.

## Reference review
Nexus Operative read-only nexus/risk_gate.py at 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11: halt/unknown veto, no trading code copied. agency-agents MIT, pinned 8ae6164602c95ca78828b148b9052460ee426885 LICENSE and strategy/coordination/handoff-templates.md inspected; bounded escalation and criteria concepts only, no prompts used as authority or dependency. Existing Exchange adaptation and PRs #2/Operative #116 inspected. Context7 CPython 3.13.14 SQLite explicit transaction/open-mode documentation reviewed for 3.10-compatible APIs.

## Limits
Local trusted directory and cooperating app versions only; not authentication, a remote/multi-tenant lock, malicious local database owner or protection from older/direct library callers. Synchronous bounded scans may require performance benchmarking on large archives. No live commercial actions, reviewer authentication, independent factual verification, new runtime dependencies, paid infrastructure or release claim. Main formal acceptance 0/42. Native Council dashboard remains separate.

## Observed verification
- Test-first ff224c4a7c6cd3f9eeb06ba942fdea819aed53de, run 45547852497: 393 tests, three failures and nine errors for missing Council recovery integration.
- Ledger maintenance fc470465a3a972f68dbdd789bc3cdc2fa5c88c67 and RuntimeGuard integration 8a93a69b57b8cc23da952bfa04cc447f8a956bfb (45547961733, both unit jobs passed).
- Desktop recovery control and smoke integration 998481d201dc396793e65cf60db8102064274d5a, run 45547992818: 393 tests on both Python versions.
- Expanded code/test head 46ef0db4cdf888606c83a70cbe18b4f70d34eee8 passed 396/396 on Python 3.10 and 3.13 (45548045184, jobs 138982269264 and 138982269693). Fifteen new tests including actual child-process crash, all-task rollback, prior v2 audit preservation, unexpected review failure halt and orphaned audit rejection.
- Draft PR #48. New Windows source/frozen smoke and exact final-head CI remain distinct verification steps. No formal gate accepted on main.
