import tempfile
import unittest
from pathlib import Path
from desktop import demo
from nexus_exchange.review_store import ReviewStore

class ReviewStoreTests(unittest.TestCase):
    def test_restart_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"reviews.sqlite3"
            reviews=demo()
            store=ReviewStore(path)
            try:
                store.save(reviews)
                store.save(reviews)
            finally:
                store.close()
            store=ReviewStore(path)
            try:
                rows=store.read()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]["amount"],"1000")
                self.assertTrue(rows[0]["eligible"])
                self.assertEqual(rows[0]["source_url"],"https://example.org/demo")
            finally:
                store.close()

    def test_invalid_batch_is_atomic(self):
        store=ReviewStore(":memory:")
        try:
            with self.assertRaises(ValueError):
                store.save((*demo(),{}))
            self.assertEqual(store.read(),())
        finally:
            store.close()
