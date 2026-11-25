# Nexus Exchange

Independent commercial intelligence and review-only intermediary workflow research.

## Development status
**Offline desktop preview; not production ready.** This integrated candidate combines Scout normalization, compiled procurement JSON imports, Council screening, Governor restrictions, SQLite task and opportunity history, Atlas matching, hypothetical fee-based economics and a desktop scenario report. Agent handoffs are a separate non-privileged review scaffold. No external commercial dispatch is implemented.

### Windows x64
Use the latest successful [Windows preview workflow](https://github.com/S4-cyber/Nexus-Exchange/actions/workflows/windows-preview.yml). Download its artifact, extract the ZIP, and verify the included SHA256.txt against NexusExchange.exe before running. Unsigned portable preview, not an installer or a signed release. No separate Python installation is required for the packaged EXE. Files are retained in the local user data directory.

### Source and testing
Python 3.10 or newer; Tkinter required for GUI. Runtime uses the standard library.

```sh
python -m unittest discover -s tests -v
python desktop.py --self-test
python desktop.py --gui-self-test
python desktop.py
```

The GUI smoke test requires a graphical environment. See [offline import](docs/OFFLINE_IMPORT.md), [deal scenario](docs/DEAL_SCENARIO.md), [Atlas](docs/ATLAS.md), [economics](docs/ECONOMICS.md), and [roadmap](docs/ROADMAP.md).

## Boundaries
Historical source assertions and simulated economics are not verified commercial facts, orders or revenue. No physical inventory, third-party fund custody, live bids, unsolicited outreach, signatures, payments or regulated brokerage without validated authority and licensing. No secrets or real counterparty data in this public repository. Keep Nexus Operative independent; reuse only audited concepts and components. No unapproved spending.

## Integration
See [integration baseline](docs/INTEGRATION_BASELINE.md) for branch lineage, acceptance criteria and known blockers. Formal release gates are separate from prototype CI.
