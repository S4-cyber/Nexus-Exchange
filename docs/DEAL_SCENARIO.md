# Offline deal simulator

1. Import a compiled procurement manifest or run the synthetic demonstration.
2. Open Opportunity archive and copy the selected opportunity key and retrieval timestamp.
3. Prepare a local UTF-8 scenario JSON file with the exact fields below, actual permitted source assertions, and explicitly supplied hypothetical economics.
4. Select **Evaluate deal scenario JSON**. Inspect the assessment and reasons. Select **Export deal report** to save the displayed report locally.

The opportunity must be among the newest 100 historical observations. The selected timestamp must match the latest archived observation for that release-scoped key. This is not a current tender index: supersession across different release IDs and provider authentication remain unresolved. A stale observation is rejected by screening. The system does not fetch URLs, contact anyone or transact.

Example manifest structure (replace the key, dates and source assertions; the sample is synthetic and not a usable live deal):

```json
{
  "format": "nexus-deal-scenario-v1",
  "opportunity_key": "COPY_64_HEX_KEY_FROM_ARCHIVE",
  "retrieved_at": "2026-11-24T12:00:00Z",
  "buyer": {
    "scheme": "EXAMPLE",
    "identifier": "buyer-1",
    "name": "Synthetic buyer",
    "roles": ["buyer"],
    "classifications": [{"scheme": "CPV", "code": "30200000"}],
    "regions": ["US-CA"],
    "currency": "USD",
    "capacity": "2000",
    "source_url": "https://example.org/buyer",
    "observed_at": "2026-11-24T12:00:00Z"
  },
  "supplier": {
    "scheme": "EXAMPLE",
    "identifier": "supplier-1",
    "name": "Synthetic supplier",
    "roles": ["supplier"],
    "classifications": [{"scheme": "CPV", "code": "30200000"}],
    "regions": ["US-CA"],
    "currency": "USD",
    "capacity": "2000",
    "source_url": "https://example.org/supplier",
    "observed_at": "2026-11-24T12:00:00Z"
  },
  "classifications": [{"scheme": "CPV", "code": "30200000"}],
  "region": "US-CA",
  "terms": {
    "currency": "USD",
    "fee_if_collected": "200",
    "upfront_cost": "20",
    "completion_cost": "40",
    "probability_completion": "0.5",
    "probability_collection_given_completion": "0.8",
    "exposure_limit": "100",
    "assumptions": "Synthetic example only."
  }
}
```

Input limit: 256 KiB. Duplicate JSON keys, malformed data and missing or superseded observations fail closed. The report records the raw input digest, evaluation timestamp, normalized observation, counterparty profiles, assumptions, exact-decimal results and rejection reasons. The digest identifies the submitted bytes; it is not proof of authentic source content. The task journal records completion or failure; full reports are exported explicitly, not automatically persisted. A successful simulation task is not a successful deal. No verified quotes or legal authority are implied.

Architecture reuse: existing strict JSON parser, OpportunityArchive, Atlas, Decimal economics, Governor, task journal and Windows GUI packaging. No copied upstream implementation or new dependency.
