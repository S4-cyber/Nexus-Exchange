# Atlas SEC EDGAR counterparty metadata (E10/E11/E12/E20/E21/E27/E38)

Base PR #62 ef5a86776db38d3fc801a11fcff6045f83fc7e07; push and PR Python CI and Windows preview passed.
Public APIs directory reference retained. Official primary documentation inspected:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- https://www.sec.gov/about/developer-resources

## Implemented candidate

Single public submissions GET to data.sec.gov/submissions/CIK##########.json,
no key, no arbitrary URL, no redirects or automatic retries. Exact positive ASCII CIK
normalized to ten digits and checked against returned filer. Only operating entities.
Owner supplies real requester organization and business contact, explicitly consents to
sending it in the required User-Agent. No requester contact in output, task target or
saved report. Optional declared company name compared locally, not transmitted.
One request in flight and one-second start spacing within this process; SEC's aggregate
10 requests/sec applies across all machines, so this is not distributed quota enforcement.
No bulk harvesting, concurrent automation, submission/filer API, paid service or new package.

Bounded JSON, duplicate-member rejection, row alignment, date/ID checks, exact selected
financial reporting forms (10-K/Q, 8-K, 20-F, 40-F, 6-K and amendments), newest 12,
explicit counts and truncation. Links reconstructed from validated identifiers; no
returned links or primary-document names trusted. No private address, phone, officer
or historical attachment data projected. Only declared/source name comparison, not
entity ownership or authenticated identity. SHA-256 of raw bytes plus observation time
and source URL; no raw source payload stored. Report stays research-only and does not
populate an Atlas supplier profile, upgrade a Council verdict, rank a lead or authorize
contact. No proof of solvency, capacity, active demand or commercial suitability.

Native Scout catalog action follows existing Governor, worker and export flow; it
shows an advisory Atlas metadata report, not a procurement lead. Explicit halt before
and after fetch; network socket timeout, not hard end-to-end deadline. No live pilot
claimed; source fixture and HTTP mocks exercise 13 regression methods and registry
status. Windows preview triggered; no deliberate failing intermediate commits.

## Next

Bind independently reviewed company metadata evidence to the exact declared Atlas
counterparty and saved opportunity, with mismatches and observation freshness surfaced.
Expand to other official company registries and permitted actual paid projects.
Separate the public-company research route from private-company verification. Do not
treat an SEC filer or name match as proof of identity, demand or revenue.
Formal main release acceptance remains 0/42; parallel correspondence work preserved.
