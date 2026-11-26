# CanadaBuys public dataset pilot

Official catalogue: https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2 ; open resource 5870de7c-86fe-4d05-8d73-cd412e12fdeb; direct CSV https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv . The federal dataset is daily, not a real-time stream or a complete catalogue of Canadian provincial/local tenders. Licence: Open Government Licence – Canada (https://open.canada.ca/en/open-government-licence-canada). Official supporting documentation and XML dictionary timed out in the research environment. The catalogue provides the direct URL and status/publication descriptions.

Reuse research: https://github.com/samarpassey/maple-procure/tree/21bd93119fd6fe2300361ac3cc6be13024af21a0 (MIT; inspected LICENSE, docs/DATA.md and src/maple_procure/sources.py). Reviewed observed bilingual column names, UTF-8 BOM, unzoned closing times, legacy links and provenance ideas. No implementation copied or dependency installed. The status field spelling differs between published catalogue text and this third-party observed schema; accept either one, reject ambiguity. Verify actual provider payload before accepting R03.

Global trade catalog -> CanadaBuys -> Search CanadaBuys. Owner consents to a single fixed-origin HTTPS GET of the open-tender CSV. 32 MiB, 20,000 rows, 128 columns, 1 MiB per field; full scan before output; title substring filter; max 75 matching leads. No retries, redirects, accounts, scraping, contact retention, arbitrary noticeURL navigation or submission. A 15-second socket timeout is not an absolute wall-clock deadline. Default TLS validation; halt checked before/after transport and periodically during CSV parse. Last-Modified is transport metadata, not independently verified publication time: missing, future or older than 48 hours blocks research candidacy. Actual source update cadence can differ.

Preserve reference, title, notice type, publication/closing dates, source URL, retrieval and snapshot digest. Never assume timezone for local closing times. Legacy references fall back to the official search page. Unknown terms, eligibility, cash exposure and exact current state remain blockers. No claim that notice budgets are revenue or that a candidate is executable. Raw personal/contact fields are not persisted or exported. No live provider request was made by this sprint's tests. Synthetic fixtures exercise bounded parsing, freshness, schema drift, duplicates, timezone handling and consent.

## GRI-8 — HTTP response completeness boundary

Shared transport requires a single bounded decimal Content-Length or a single
chunked Transfer-Encoding, not both, and accepts only absent or identity
Content-Encoding. Reject close-delimited, duplicate, ambiguous or oversized
declared bodies before reading; verify the actual fixed-length byte count and
cap the decoded chunked body. The Python standard-library chunk parser handles
chunk decoding and raises on interrupted chunks. This avoids treating a
valid-looking truncated CSV prefix as a complete dataset. Framing is not
proof of source-level completeness or authenticity; live provider/proxy
compatibility remains unverified, and the socket timeout is not a hard wall
deadline. No live provider requests were made.

Five new fixture methods, real HTTPResponse with owned in-memory bytes and
mocked opener. On Python 3.13.5: 12 expected red failures on original source,
then all nine focused methods passed with the corrected source. Exact base
and new source/test blobs checked; full local checkout DNS remains blocked.
Hosted integration and independent review still required.
