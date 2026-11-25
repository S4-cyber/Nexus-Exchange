# Nexus Exchange

Independent commercial intelligence and review-only intermediary workflow research.

## Development status
**Consolidated offline release-review candidate; not production ready.** Scout has bounded consented read-only research adapters and historical lead memory, capability-aware review, Council evidence/attempt tracking, Governor halt/recovery, Atlas matching and four local Operator services (CSV standardization, JSON-to-CSV conversion, column quality reporting, two-file reconciliation), exact Scout review handoff, scoped artifact registration, QA, obligations, correspondence history and simulated receivables/cash-flow allocation. An isolated owned Genesis diagnostic exercises discovery through simulated settlement and restart. No verified real income or external commercial dispatch is implemented. See [release review and unresolved gates](docs/RELEASE_REVIEW.md).

Scout's **Capability search planner** builds explicit read-only search options from the current declared owner profile and implemented Operator service. See [capability discovery](docs/SCOUT_CAPABILITY_DISCOVERY.md). In the manual planner each search requires separate consent; no automatic outreach or transactions. Completed capability searches are recorded with their archive observations and recent repeat hints; see [search history](docs/SCOUT_SEARCH_HISTORY.md). The [search performance](docs/SCOUT_DISCOVERY_PERFORMANCE.md) view orders unchanged local search options using bounded, archive-consistent historical evidence.

### Engage on Windows

Select **Engage** on Home. Scout immediately searches UK Find a Tender and CanadaBuys, archives observations, checks capability and source holds, and compiles a review brief. An optional SAM.gov key adds federal solicitations. Existing search preferences take precedence. Scout repeats one hour after each completed cycle while the desktop is open. Emergency halt cancels future cycles and interrupts active work at its next checkpoint. A restart opens paused and retains the latest completed brief.

For local production, place a UTF-8 CSV in **Settings → Open work inbox**. Each cycle computes column-quality metrics and independently checks the output. **Open completed files** shows the reports. Each input is limited to 256 KiB, 2,000 records and 16 uniquely named columns. Headers use letters, digits and underscores and start with a letter. Cells are limited to 256 printable characters and formula-shaped values are held. Existing identical results are reused. Raw inputs stay on the device.

**Accounts** stores credentials under the current Windows user's DPAPI protection. A SimpleFIN Bridge setup token grants balance access. Catalyst planning uses the lower of the declared ceiling and one fresh USD available balance, with a zero fallback. Multiple connected accounts, missing available balances and readings over 24 hours old leave the limit at zero. The application cannot move funds. To enable DocuSign, the publisher registers a production native public OAuth integration with PKCE and callback `http://127.0.0.1:54381/callback`, then supplies its public client ID via `NEXUS_DOCUSIGN_CLIENT_ID` or at first connection. Consent checks account identity and renews while engaged. External document dispatch, contract execution and settlement are pending product capabilities. Forget removes local credentials. The provider manages revocation.

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
