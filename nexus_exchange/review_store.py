"""Local append-only screening evidence; never grants commercial authority."""
import json
import sqlite3
import hashlib
from .pipeline import Review

class ReviewStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.commit()

    def save(self,reviews):
        rows=[]
        for review in reviews:
            if type(review) is not Review:
                raise ValueError("normalized review required")
            o=review.observation.opportunity
            payload=json.dumps(dict(key=o.key,source=o.source,external_id=o.external_id,
                title=o.title,source_url=o.source_url,retrieved_at=o.retrieved_at.isoformat(),
                deadline=o.deadline.isoformat() if o.deadline else None,currency=o.currency,
                amount=str(o.amount) if o.amount is not None else None,
                release_key=review.observation.release_key,
                published_at=review.observation.published_at.isoformat(),
                eligible=review.screening.eligible_for_review,reasons=review.screening.reasons),
                sort_keys=True,allow_nan=False)
            rows.append((hashlib.sha256(payload.encode()).hexdigest(),payload))
        with self.db:
            self.db.executemany("INSERT INTO reviews VALUES (?,?) ON CONFLICT(id) DO NOTHING",rows)

    def read(self):
        return tuple(json.loads(row[0]) for row in self.db.execute("SELECT payload FROM reviews ORDER BY rowid"))

    def close(self):
        self.db.close()
