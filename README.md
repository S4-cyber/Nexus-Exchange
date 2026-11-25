# Nexus Exchange

Independent commercial intelligence and review-only intermediary workflow research.

## Development status
**Consolidated offline release-review candidate; not production ready.** Scout has bounded consented read-only research adapters and historical lead memory, capability-aware review, Council evidence/attempt tracking, Governor halt/recovery, Atlas matching and four local Operator services (CSV standardization, JSON-to-CSV conversion, column quality reporting, two-file reconciliation), exact Scout review handoff, scoped artifact registration, QA, obligations, correspondence history and simulated receivables/cash-flow allocation. An isolated owned Genesis diagnostic exercises discovery through simulated settlement and restart. No verified real income or external commercial dispatch is implemented. See [release review and unresolved gates](docs/RELEASE_REVIEW.md).

Scout's **Capability search planner** builds explicit read-only search options from the current declared owner profile and implemented Operator service. See [capability discovery](docs/SCOUT_CAPABILITY_DISCOVERY.md). In the manual planner each search requires separate consent; no automatic outreach or transactions. Completed capability searches are recorded with their archive observations and recent repeat hints; see [search history](docs/SCOUT_SEARCH_HISTORY.md). The [search performance](docs/SCOUT_DISCOVERY_PERFORMANCE.md) view orders unchanged local search options using bounded, archive-consistent historical evidence.

### Engage on Windows

Select **Engage** on Home. Scout immediately searches UK Find a Tender and CanadaBuys, archives observations, checks capability and source holds, and compiles a review brief. An optional SAM.gov key adds federal solicitations. Existing search preferences take precedence. Scout repeats one hour after each completed cycle while the desktop is open. Emergency halt cancels future cycles and interrupts active work at its next checkpoint. A restart opens paused and retains the latest completed brief.

Home and Reports both show **live activity** while work runs. Search the list by task, finding, source, date or detail, or filter by status. Selecting a row shows its details in place. Scout updates each task as it moves from pending to engaged to complete, and records findings once their source observations are archived. The next scheduled cycle appears while Scout is waiting. Reports also contains the latest brief, work-file results and the current manual search result. The local feed retains the most recent 5,000 detailed items plus active work. It also shows the latest status for tasks in the newest 5,000 journal events. Restarting marks unfinished work as stopped.

For local production, open **Reports → Work files → Open inbox**. Each cycle checks CSV columns and converts flat JSON records into CSV. JSON inputs use a list of objects with identical field names and text values. The output preserves the record order, duplicate records, and first record's column order. Select an input in Work files to see the verified output filename or the reason it needs attention. **Open completed files** opens the output folder. Inputs stay on the device and are limited to 256 KiB, 2,000 rows and 16 columns. Use unique field names starting with a letter and containing letters, digits or underscores. Each cell accepts up to 256 printable characters. Formula-like cells are held. Later cycles reuse matching outputs and preserve edited copies.

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

## Development resource library

See the [Awesome engineering resource catalogue](resources/awesome/README.md) for pinned references, offline filtering, and a gated local-agent adoption plan. Nothing in the catalogue grants runtime authority or installs dependencies.

Development workspace instructions: [AGENTS.md](AGENTS.md) and [development protocol](docs/DEVELOPMENT_PROTOCOL.md).
