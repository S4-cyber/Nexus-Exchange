# Capability search history and repeat hints

Base #90 7b891d4ff0ecc44d3fa81222e052f3e43f9170da passed both Python suites (783 tests) and full
Windows verification (45649247055).

Completed capability-planner searches now write a bounded receipt in the
existing scout-leads.sqlite3 database, in the same transaction as their
parsed observations. Each receipt binds the journal task ID, exact reviewed
plan and option, profile revision and catalogue digest, fixed query scope,
UTC start/completion, page digests, canonical projected observation-set
digest, request count, returned/new-observation counts and truncation flag.
It matches the adapter report's source/query and Contracts Finder local CPV
before commit. Zero-result searches retain a receipt; failed, unarchived or
manual non-planner searches do not. A pre-commit halt or failed receipt
rolls back the transaction. Duplicate task IDs fail; repeat searches with
new task IDs remain allowed. No source text, credentials, complete profile,
raw response or arbitrary URL is stored in receipts. No new database file;
existing backups retain the added table, and old archives open without
rewriting historical rows. Maximum 2,000 receipts; no automatic deletion.
The local trusted database and digest are not authentication or an audit
of provider availability. A halt immediately after commit may leave a
complete receipt and observations, even if the dashboard withholds output.

The native planner shows up to 100 newest completed receipts and warns of
an exact query or overlapping comparable window within 15 minutes,
including truncation and new-observation counts. Comparison uses actual
provider filters rather than capability labels; broad release searches can
overlap across services. No automatic skip, cached current status, new
network request or bypass of per-search consent. Older history and other
manual queries may not be represented. The owner may explicitly repeat
any valid query. Source holds and existing archive validation are unchanged.

Seven focused regression methods cover real owned parser report, atomic
rollback, duplicate task handling, empty results, halt/capacity, tamper
denial and advisory repeat classification. Native owned smoke opens
history without contacting a provider. Hosted exact-head verification
required. No live commercial action, new dependency or cost; no main
merge or formal release acceptance.
