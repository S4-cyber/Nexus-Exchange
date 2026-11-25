# Historical search performance and advisory ordering

Base #92 1af21584b934fb99c78b4a33619a2f34994dbcab, archive-evidence resolution and Python CI passed.
#91 full Windows passed (45650359330); #92 Windows was pending at preflight.

The planner's Search performance view summarizes the latest 100 displayed
receipts, up to seven days, restricted to the exact current profile and
capability catalogue. Only locally archive-consistent v2 receipts are
used; legacy, future-dated, older and mismatched-profile/catalogue records
are excluded and counted. The projection validates receipt metadata and
digest, but the trusted LeadStore read establishes local archive
consistency; this is not independent provider authentication.

Comparable provider filters (source, filter kind/value and procurement
type) share history. Complete collections contribute distinct source/key
notice identities divided by total complete-search requests, not counts of
fresh observations. A repeated notice does not inflate that numerator.
This is not cross-source deduplication, current opportunity eligibility,
market demand, a probability of winning or a revenue prediction. Incomplete
collections are separately counted, including their returned/inserted
observations, but do not contribute to measured yield. The bounded history
can omit prior work and never includes failed or non-planner searches.

Unchanged ready options are ordered: measured filters (at least three
complete searches; higher distinct-notice/request ratio first), unmeasured
exploration, small samples, incomplete-only collection review, recent
repeat review, then held options. Ties use stable option identity. The
first measured/exploration/small-sample row is a suggested review only;
no suggestion if all options are held/recent/incomplete-only or the plan
has expired. A recent receipt is not a cache hit or a prohibition. Every
search still requires the exact existing reviewed plan and separate owner
consent; the original sealed plan is not changed. No automatic dispatch,
skipping, credential storage or provider calls. No new database or
dependencies. Seven regression methods and extended owned native smoke.
No main merge or formal gate promotion.
