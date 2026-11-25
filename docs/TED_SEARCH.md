# TED anonymous search pilot

Official references: https://docs.ted.europa.eu/api/latest/search.html ; https://docs.ted.europa.eu/ODS/latest/reuse/search-api.html ; https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html .

In Global trade catalog select EU TED, then Search EU TED (keyless). Enter a CPV prefix (72 IT services, 79 business services), and consent to one search. The preview searches the last 14 days, at most three requests including one transient retry, 25 notices per page. Fixed TLS host and published-notice search endpoint only. POST means a read-only search here, not publication or submission. No key, account, new paid infrastructure, or financial commitment.

Reports preserve public notice identifiers, titles, CPV classifications, publication and reported lot deadline dates, attribution, retrieval times and page digests. Exact deadline timestamps and current version are unverified; separate lot dates/times are never guessed or combined. Estimated procurement budgets are not revenue. All results are research only with lead-specific To Do items, unknown cash exposure, and no execution authority. No automated scheduling or live bidding.

Mock acceptance: scope and consent, bounded query and pages, response validation, language fallback, deadline/type screening, duplicate detection, redaction and origin restrictions. Live production schema and search behavior remain to be verified in an authorized read-only pilot; public search documentation is not proof of connectivity. Neither supplier eligibility nor European delivery/financial/legal suitability has been certified.
