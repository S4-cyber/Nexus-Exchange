# Nexus Exchange

Independent commercial intelligence and review-only intermediary workflow research.

## Development status
**Consolidated offline release-review candidate; not production ready.** Scout has bounded consented read-only research adapters and historical lead memory, capability-aware review, Council evidence/attempt tracking, Governor halt/recovery, Atlas matching and four local Operator services (CSV standardization, JSON-to-CSV conversion, column quality reporting, two-file reconciliation), exact Scout review handoff, scoped artifact registration, QA, obligations, correspondence history and simulated receivables/cash-flow allocation. An isolated owned Genesis diagnostic exercises discovery through simulated settlement and restart. No verified real income or external commercial dispatch is implemented. See [release review and unresolved gates](docs/RELEASE_REVIEW.md).

### Windows x64
Use an explicitly identified successful [Windows preview workflow](https://github.com/S4-cyber/Nexus-Exchange/actions/workflows/windows-preview.yml), not simply the newest run across unrelated branches. Download its artifact, extract the ZIP, compare SHA256.txt against NexusExchange.exe with PowerShell Get-FileHash, and check PREVIEW.json against the workflow's actual checkout and run. New bundles also include the owned source GENESIS.json diagnostic. See the [preview verification and recovery runbook](docs/RELEASE_REVIEW.md). Unsigned portable preview, not an installer or signed release; checksums are not publisher authentication. No separate Python installation is required for the EXE.

### Source and testing
Python 3.10 or newer; Tkinter required for GUI. Runtime uses the standard library.

```sh
python -m unittest discover -s tests -v
python desktop.py --self-test
python desktop.py --gui-self-test
python desktop.py --fixture-process-self-test
python desktop.py --genesis-self-test
python -m nexus_exchange.genesis_diagnostic
python desktop.py
```

The GUI smoke test requires a graphical environment. See [offline import](docs/OFFLINE_IMPORT.md), [deal scenario](docs/DEAL_SCENARIO.md), [Atlas](docs/ATLAS.md), [economics](docs/ECONOMICS.md), and [roadmap](docs/ROADMAP.md).

## Boundaries
Historical source assertions and simulated economics are not verified commercial facts, orders or revenue. No physical inventory, third-party fund custody, live bids, unsolicited outreach, signatures, payments or regulated brokerage without validated authority and licensing. No secrets or real counterparty data in this public repository. Keep Nexus Operative independent; reuse only audited concepts and components. No unapproved spending.

## Integration
See [integration baseline](docs/INTEGRATION_BASELINE.md) for branch lineage, acceptance criteria and known blockers. Formal release gates are separate from prototype CI.
