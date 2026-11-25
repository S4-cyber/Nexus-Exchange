import unittest
from nexus_exchange.ocds_snapshots import select_snapshots

class SnapshotTests(unittest.TestCase):
    def test_latest_cancelled_preserved(self):
        a=dict(ocid="x",id="1",date="2026-01-01T00:00:00Z",tender={"status":"active"})
        b=dict(a,id="2",date="2026-01-02T00:00:00Z",tender={"status":"cancelled"})
        self.assertEqual(select_snapshots("p",[b,a]),(b,))
    def test_conflicting_identity(self):
        a=dict(ocid="x",id="1",date="2026-01-01T00:00:00Z")
        with self.assertRaises(ValueError): select_snapshots("p",[a,dict(a,title="changed")])
    def test_tied_time(self):
        a=dict(ocid="x",id="1",date="2026-01-01T00:00:00Z")
        with self.assertRaises(ValueError): select_snapshots("p",[a,dict(a,id="2")])
