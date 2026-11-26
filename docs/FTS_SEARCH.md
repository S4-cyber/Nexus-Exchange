# UK Find a Tender — public OCDS release pilot

Primary sources: https://www.gov.uk/government/publications/open-contracting ; https://www.gov.uk/government/publications/procurement-act-2023-short-guides/buyers-and-suppliers-how-to-use-the-central-digital-platform-the-enhanced-find-a-tender-service-html ; https://standard.open-contracting.org/latest/en/schema/reference/ . Official endpoint help https://www.find-tender.service.gov.uk/apidocumentation/1.0/GET-ocdsReleasePackages was inaccessible (403) in the research environment. Parameter and cursor details corroborated by https://www.webtruffle.com/learn/find-a-tender-ocds-api ; live contract/schema validation remains required.

Global trade catalog -> UK Find a Tender -> Search UK FTS. Explicit owner consent for one last-24-hour search. Uses fixed HTTPS GET /api/1.0/ocdsReleasePackages, frozen updatedFrom/updatedTo strings, no stage filter, limit 25, at most three requests including one transient retry. UTC is a disclosed assumption for timezone-less update filters. Cursor is treated as opaque; only same host/path and unchanged known parameters accepted, requests rebuilt from fixed origin. No credentials or commercial dispatch; no redirect or arbitrary attachment fetching. One-second spacing and ten-second socket timeout, not a hard wall-clock limit. Provider quota and exact pagination behavior not yet confirmed live.

Preserves release-scoped identity (publisher, OCID, release ID), notice URL, release date, tags and reported tender deadline. Does not persist raw party/contact data, assume award value is compensation, or mix release events into the compiled OCDS archive. Within the collected window, older releases are marked superseded, ties blocked, and all candidates blocked if a continuation remains at the request cap. A completed update-window scan still does not establish full process history; even an active tender event is only a research lead. Full record-package rehydration and OCDS compilation, durable evidence retention and source-specific qualification are still required.

Tests cover lifecycle, cursor validation and bounds, consent, provenance, duplicates, response limits, retry and halt. Source terms allow data reuse under OGL 3.0; attribution included. No live request was made in development or CI. User-machine and provider schema testing remain pending.

## GRI-8 — fixed query transport boundary

The shared UK public-feed transport now independently admits exactly the
adapter's updatedFrom/updatedTo, fixed page limit and optional opaque
cursor. Reject extra/missing fields, non-string values, malformed dates,
nonpositive or over-seven-day serialized windows, and out-of-grammar
cursors before constructing a request. A subsecond interval that truncates
to equal whole-second bounds is intentionally refused. Canada remains
parameter-free. No provider access or credential was used. The existing
origin, redirect denial, body caps, socket timeouts and adapter consent
checks remain unchanged. This is defense in depth, not verified provider
authorization, nor a wall-clock deadline.

Four focused tests (real exact baseline transport module, inspected adapter
constants substituted locally, mocked HTTP opener): 12 assertion failures
before correction, all four methods passed afterward on Python 3.13.5.
Full local repository checkout failed DNS resolution; hosted integration and
independent review remain required.

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
