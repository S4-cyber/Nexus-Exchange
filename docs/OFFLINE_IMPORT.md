# Offline procurement import

Use the desktop **Import compiled JSON** button to select a local UTF-8 JSON file containing an explicitly prepared Nexus compiled-snapshot manifest. The application does not fetch the source URL. Only compiled snapshots are supported; raw release packages and incremental OCDS updates are not interchangeable with compiled releases.

```json
{
  "format": "nexus-compiled-snapshots-v1",
  "publisher": "example-publisher",
  "source_url": "https://example.org/procurement",
  "retrieved_at": "2026-11-24T12:00:00Z",
  "releases": [
    {
      "ocid": "ocds-example-1",
      "id": "compiled-1",
      "date": "2026-11-24T10:00:00Z",
      "tag": ["compiled"],
      "tender": {
        "status": "active",
        "title": "Illustrative opportunity",
        "value": {"amount": 1234.50, "currency": "USD"},
        "tenderPeriod": {"endDate": "2027-01-01T00:00:00Z"}
      }
    }
  ]
}
```

This is synthetic example data, not an actual procurement listing. Replace with permitted source observations, genuine retrieval time and accurate provenance. Review eligibility can become stale; it grants no authority to bid or contact anyone. Limits: 2 MiB, 1–100 releases, supported numeric precision, complete active tender fields; invalid records fail the batch. Source URLs, timestamps and compiled tags are assertions, not authentication or complete OCDS schema validation. No original file digest or document bytes are persisted. Use Opportunity archive to inspect and export recent historical observations.

Reference: https://standard.open-contracting.org/latest/en/schema/records_reference/
