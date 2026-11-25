# Public APIs adoption — commercial research and reference data (E10/E11/E12/E20/E21/E22/E26/E38)

Directory: https://github.com/public-apis/public-apis/tree/9fb3bdb62643400aaebee03a2ecce0cd1ec934eb
Reviewed README categories Business, Government, Jobs, Finance, Currency Exchange, Calendar,
Open Data, Documents & Productivity. Pinned revision dated 2026-11-22. Directory MIT license
reviewed; entries are leads, not service grants or a bundled API. No upstream code or whole
directory copied. Provider terms override directory metadata; directory authors are not
service providers. Reviewed 2026-11-24.

## Integration matrix

| Provider | Nexus use | Stage / official evidence |
|---|---|---|
| Frankfurter | Council/Genesis/Catalyst indicative cross-currency comparison | v2 single-pair adapter and native explicit lookup; fixture tests, live pilot pending. https://frankfurter.dev/ and https://frankfurter.dev/license/ |
| Freelancer | Scout digital paid-project discovery | Candidate only; verify API license, platform AI use, fees, actual project and written permission where required. https://www.freelancer.com/about/apiterms |
| Adzuna | Human employment research, not contracts | Restricted; commercial lead generation requires written agreement. https://developer.adzuna.com/docs/terms_of_service |
| Tenders.guru | Secondary cross-country procurement research | Directory lead only: Hungary, Poland, Romania, Spain, Ukraine; verify service and original official sources. https://tenders.guru/pl/api |
| SEC EDGAR | Atlas entity filings, counterparty research | Bounded read-only CIK metadata adapter and explicit native lookup; mock-tested candidate, live pilot pending. No key for data.sec.gov, declared user agent/contact and fair access; do not exceed SEC's aggregate request limit. https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data |
| UK Companies House | Atlas company-number matching | Authentication required; official records not legal clearance. https://developer.company-information.service.gov.uk/authentication/ |
| US Census | Market sizing by sector and geography | Free key required for all data queries per updated 2026 guidance, despite directory metadata. https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html |
| World Bank Indicators | Macroeconomic reference data, not tenders | Keyless v2; candidate. https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation |
| UK Bank Holidays | Local schedule context | Official regional calendar; attribution/license and contractual calendar review required. https://www.gov.uk/help/reuse-govuk-content |

Existing USAspending and Upwork entries retained; no duplicate provider. Future provider
screening: invoice format validation (no private document uploads until reviewed), official
property/parcel datasets (no ownership profiling or brokerage), trade statistics, patent
research, permitted digital task platforms, and official primary procurement feeds. Do not
automatically ingest the changing upstream list or treat paid/trial APIs as free.

## Implemented

33 native catalog entries (24 existing + 9 added). Status and source-specific To Do remain
separate from revenue qualification. Frankfurter v2 single GET to a fixed host/path; seven
non-USD currencies to USD, no arbitrary URL, no amount or private profile sent, no account,
no redirect-follow/retry. Trusted UI confirmation, existing worker admission and halt before
and after retrieval. Bounded JSON with duplicate-member checks, exact requested currency
pair, maximum seven calendar days of reference age, Decimal arithmetic and half-even cents
for display. Report preserves original amount, exact modeled USD, source URL/date/retrieval
time and raw payload fingerprint. Blended reference rates are not official tax/accounting
fixings, payment quotes or executable market rates; no margin, cost, liquidity or collection
verification. Native report is advisory and does not overwrite saved scenario values,
alter rankings, qualify Genesis, or persist a lead. No API credentials or new dependencies.

Eleven FX regression methods and one registry regression method, fixed-host HTTP mocks,
malformed/stale/wrong-pair checks, halt, no retries, bounds and exact arithmetic. Windows
preview scope expanded; no live API call in automated CI.

## Next

Prioritize Freelancer-approved project research and primary official tenders; add SEC
CIK-based bounded retrieval after declared contact configuration; integrate FX evidence
with an explicitly selected saved scenario only after reviewing multi-currency cash-risk
semantics. Keep branch isolated from parallel correspondence PR #60. No main merge or
formal release gate change. Local checkout not claimed; exact-head CI must verify.
