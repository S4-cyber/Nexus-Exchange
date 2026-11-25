# Scout UK Contracts Finder — official paid service release discovery

E10/E11/E12/E18/E22/R06. Base PR #63 31813c7e47629b806b93d545397032a1cd9ea940; both Python CI runs passed.
Freelancer remains gated: user agreement section 33 expressly requires written permission
for automated access including APIs; API terms also restrict storage, redistribution,
competitive use and reliance. No live request or marketplace data retained.
https://www.freelancer.com/about/terms and https://www.freelancer.com/about/apiterms.

Official source: https://www.gov.uk/government/publications/open-contracting
Real published schema reference: https://www.data.gov.uk/dataset/f1047969-1d3b-4c34-bc7f-ed0f3cad5419/contracts-finder-notices-06-20261/datafile/a92ddddb-11f9-4f40-af4c-872f9e06110d/preview
Source API documentation link returned 403 to development reader; official overview and
published 2026 sample show release GUID-version identity and OCDS 1.1 fields; current
limit/cursor parameter pattern additionally documented by open data consumers. Live pilot
and precise provider boundary behavior remain unverified.

## Candidate
- Fixed public keyless GET for publication window of 1–24 hours and max 50 rows, max 4 MiB,
  no redirects, retry, or automatic pagination. All stages retained to detect contrary
  events, CPV filter local. Provider continuation or full page holds every result;
  never follow returned URLs. Process-local 3.1-second spacing, 5-minute cooldown after
  403/429/503; no distributed quota guarantee.
- Strict provider OCID and release GUID-version identity; reconstruct notice link from
  GUID rather than accepting returned links. Preserve distinct release versions and
  newest known process event; same-time ambiguity holds. Missing active status,
  deadline, service classification or mismatched prefix holds. No raw contact,
  descriptions, documents, value or currency treated as revenue. No complete process
  compilation or independent verification. Attribution: Cabinet Office / Contracts Finder,
  OGL v3.0 https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/.
- Source-specific consent and halt before/after request; existing native Scout worker,
  source results, durable historical archive and owner CPV capability profile. New
  source ID uk_contracts; distinct release versions are retained and known later
  events block older observations across sessions. Existing profiles remain compatible;
  user must explicitly select the new source in profile before ranking it.
- Twelve regression methods including real archive/profile integration, later award,
  scope, bounds, throttle, malformed responses and explicit written-permission gate.
  Windows preview triggered; no live provider calls or local checkout test claimed.

Next: live read-only pilot with owner approval; validated continuation/full record
compilation, cross-portal deduplication, and independently reviewed zero-capital
delivery terms. Continue direct digital project pathways without violating provider
agreements. No new paid resources, bids or authority; main release acceptance 0/42.
