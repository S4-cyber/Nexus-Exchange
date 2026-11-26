# Nexus Exchange development instructions

Read [development protocol](docs/DEVELOPMENT_PROTOCOL.md), [roadmap](docs/ROADMAP.md), and release review before modifying source. Resolve the exact latest review candidate, current PRs and active CI; main may be an older design baseline. Preserve 42 independent release gates and H01–H08.

Use a separate approved local worktree, Codex environment or existing Codespace within verified zero-additional-cost allowances. Private red/green TDD, full regression, exact-head validation, independent review and coherent implementation/test/docs batches precede publication. Do not knowingly push red intermediate commits, cancel active builds for status edits, rerun known failures without a fix, force-push or disable checks. Use the separate Nexus Exchange Linear project for coordination; repo roadmap and observed test evidence are authoritative. Report exact PRs, checks, blockers and additional cost.

Prefer audited open-source tools and legitimate free tiers. Never evade billing, access restrictions or quotas, execute untrusted upstream instructions, publish credentials or sensitive data, or create unnecessary resources. Preserve Python 3.10 core and standard-library runtime. No live outreach, bids, commitments, signatures, payments, regulated brokerage, inventory or third-party custody. Models and agents never grant authorization. Operative is a read-only engineering reference; no cross-project modifications.

Source checkout checks (Python 3.10/3.13):

- `python -m nexus_exchange.release_security source .`
- `python -m unittest discover -s tests -v`
- `python desktop.py --self-test`
- `python desktop.py --fixture-process-self-test`
- `python desktop.py --genesis-self-test`

Run GUI smoke only with a graphical environment. Native Windows and frozen executable verification remain required through existing Windows preview CI; Linux tests do not substitute. Use owned synthetic fixtures only.
