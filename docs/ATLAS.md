# Atlas: counterparty qualification

Atlas accepts a normalized Scout opportunity, a declared buyer profile, up to 100 declared supplier profiles, explicit required item classification codes and a delivery region. It returns deterministic, reason-coded candidates for human review. No network access, communications, transactions or external authority.

Profiles contain a registry scheme and organization identifier, name, roles (buyer/supplier), item classification scheme/code pairs, supported regions, currency, positive capacity as decimal text, source URL and observation timestamp. Identity is scoped to registry and identifier, never inferred from names. Capacity is a declared maximum in the opportunity currency, not verified credit, a supplier quote or an agreed price.

The caller must supply requirements and region explicitly; they are not inferred from title text. Matching requires exact classification coverage and region, same currency, sufficient declared capacity, distinct identities, valid roles and fresh observations. Council's opportunity freshness, deadline and value screening also applies. Missing or malformed required fields reject the batch. Aliases across registries, actual legal identity, beneficial ownership, consent, sanctions, licenses, credit, service availability and opportunity-to-buyer ownership require further verification. Eligibility is only a review suggestion, not an endorsement, order, bid or permission.

## Architecture references
- Open Contracting Data Standard v1.1.5: https://standard.open-contracting.org/latest/en/schema/reference/
- Organization identifiers: https://standard.open-contracting.org/latest/en/guidance/map/organization_identifiers/
- Role codelists: https://standard.open-contracting.org/latest/en/schema/codelists/

Adopts scheme-scoped identifier and classification concepts, not copied implementation code or a full OCDS profile. No extra dependencies. Use synthetic examples only in public tests.

## Next
Source-specific organization adapters; independently verified organization linkage and classification requirements; bounded profile persistence; matching UI and explicit human review; quote-based risk-adjusted economics. Never use tender budget as guaranteed revenue.
