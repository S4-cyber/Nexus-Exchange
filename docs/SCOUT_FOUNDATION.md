# Scout foundation and reuse audit — 2026-11-24

Exchange main inspected at 261a3343de17b537594a333133b9ad118442e6cc: README, roadmap only; no open issues, PRs or observed Actions runs at inspection. Operative reference pinned to commit 6a1df5c2003ae6fa3f3536f5cdd72ab7ddfbfa11 (review/v0.340.381-cross-session-coverage).

Candidate review:
- council.py (2afb229bebb66ee49c87d6495fc9e7ef311bbc9a): deterministic reason-coded research, financial/trading assumptions unsuitable for direct commercial use.
- risk_gate.py (ab737fdd8fae557ef456e3240d6580fc35d9e459): fail-closed input checks; depends on paper_execution. Reimplement generic principles rather than importing.
- journal.py (59ee08e7734347897b29af33603dffba783ec9ad): SQLite audit persistence with filesystem guards; depends on sqlite_journal_guard. Defer storage and review transitive security requirements.
- pyproject.toml (d231147a8765d999efe85e17ce3f36976bd1dda7): dependencies include FastAPI, uvicorn, Pydantic, cryptography, pywebview and keyring. None needed for Scout slice. LICENSE path returned 404; full licensing and security review not complete. No Operative source copied or modified.

Scout is dependency-free Python 3.10+. Run from repository root:

    python -m unittest discover -s tests -v

Input is exact dict schema with source, external_id, title, source_url, retrieved_at, deadline, currency, amount. Last three may be null (currency/amount together). Currency validates format, not ISO membership. Amount is decimal text, no conversion or assumption of known value. Timestamps require offset and normalize UTC. URL stored as an assertion only, never fetched or treated as proof. Future connectors must validate allowed host, sanitize secrets and reject unsafe redirects. Dedup uses source+external_id; newest retrieved observation wins, equal-time conflicts fail. All input is untrusted and no external actions exist. The dataclass is not an authorization token.

Local Python 3.13 tests: initial missing module failure, then six passing tests including 20 malformed-record subcases. Local git blob IDs: scout.py 1c3d5a1088d2ed8436ba65d6ec722bb9f59a521a; test_scout.py bdaa02429815a3c8cf4931dbba9b36a353cf2285. Verify remote blob equality before relying on these results. Hosted CI remains pending.
