"""Historical observation archive, not an active tender index or verified evidence.

Trusted local single-user storage only. No raw source documents, network access,
commercial permissions, or persistent eligibility decisions.
"""
import json
import sqlite3
import re
from datetime import datetime
from .scout import normalize, Opportunity, _timestamp
from .ocds_adapter import TenderObservation
from .pipeline import Review
from .council_screen import screen

MAX_ROWS = 10_000
MAX_BATCH = 100

def _encode(item):
    if type(item) is not TenderObservation or type(item.opportunity) is not Opportunity:
        raise ValueError("normalized tender observation required")
    o = item.opportunity
    if type(item.release_key) is not str or not re.fullmatch("[0-9a-f]{64}", item.release_key):
        raise ValueError("invalid release key")
    if item.release_key != o.external_id:
        raise ValueError("release key mismatch")
    if type(item.published_at) is not datetime or item.published_at.utcoffset() is None:
        raise ValueError("aware publication required")
    if type(o.retrieved_at) is not datetime or o.retrieved_at.utcoffset() is None:
        raise ValueError("aware retrieval required")
    raw = dict(source=o.source, external_id=o.external_id, title=o.title,
        source_url=o.source_url, retrieved_at=o.retrieved_at.isoformat(),
        deadline=o.deadline.isoformat() if o.deadline is not None else None,
        currency=o.currency, amount=format(o.amount,"f") if o.amount is not None else None)
    canonical = normalize(raw)
    if canonical != o:
        raise ValueError("noncanonical opportunity")
    published = _timestamp(item.published_at.isoformat())
    if published > canonical.retrieved_at:
        raise ValueError("future publication")
    # Use normalized timestamps and canonical decimal text for idempotency.
    raw["retrieved_at"] = canonical.retrieved_at.isoformat()
    raw["deadline"] = canonical.deadline.isoformat() if canonical.deadline is not None else None
    if canonical.amount is not None:
        raw["amount"] = format(canonical.amount,"f")
        if "." in raw["amount"]:
            raw["amount"] = raw["amount"].rstrip("0").rstrip(".")
    payload = json.dumps(dict(raw=raw,published_at=published.isoformat()),
        sort_keys=True,separators=(",",":"),allow_nan=False)
    return canonical.key, raw["retrieved_at"], payload

class OpportunityArchive:
    def __init__(self,path):
        self.db = sqlite3.connect(path,timeout=5,isolation_level=None)
        try:
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS observations_v1 (
                opportunity_key TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(opportunity_key,retrieved_at))""")
        except BaseException:
            self.db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.db.close()

    def record(self, observations):
        if type(observations) not in (list,tuple) or len(observations)>MAX_BATCH:
            raise ValueError("bounded observation batch required")
        rows = [_encode(item) for item in observations]
        inserted = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            count = self.db.execute("SELECT COUNT(*) FROM observations_v1").fetchone()[0]
            for key,stamp,payload in rows:
                prior = self.db.execute("SELECT payload FROM observations_v1 WHERE opportunity_key=? AND retrieved_at=?",
                    (key,stamp)).fetchone()
                if prior is not None:
                    if prior[0]!=payload:
                        raise ValueError("conflicting observation")
                    continue
                if count+inserted>=MAX_ROWS:
                    raise ValueError("archive capacity review required")
                self.db.execute("INSERT INTO observations_v1 VALUES (?,?,?)",(key,stamp,payload))
                inserted += 1
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return inserted

    def recent(self,*,now,limit=20):
        """Return historical observations, re-screened at explicit evaluation time."""
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid history limit")
        if type(now) is not datetime or now.utcoffset() is None:
            raise ValueError("aware evaluation time required")
        result=[]
        rows=self.db.execute("""SELECT opportunity_key,retrieved_at,payload FROM observations_v1
            ORDER BY julianday(retrieved_at) DESC,retrieved_at DESC,opportunity_key LIMIT ?""",(limit,))
        for key,stamp,payload in rows:
            data=json.loads(payload)
            o=normalize(data["raw"])
            item=TenderObservation(o,o.external_id,_timestamp(data["published_at"]))
            if _encode(item)!=(key,stamp,payload):
                raise ValueError("invalid stored observation")
            result.append(Review(item,screen(o,now=now)))
        return tuple(result)
