import unittest
from nexus_exchange.ocds_identity import release_identity

class IdentityTests(unittest.TestCase):
    def test_scope(self):
        r={"ocid":"ocds-test-1","id":"release-1"}
        self.assertEqual(release_identity("publisher",r),release_identity("publisher",dict(r,title="new")))
        self.assertNotEqual(release_identity("publisher",r),release_identity("other",r))
        self.assertNotEqual(release_identity("publisher",r),release_identity("publisher",dict(r,id="release-2")))
    def test_invalid(self):
        for r in ({}, {"ocid":"x","id":"#bad"},{"ocid":True,"id":"a"}):
            with self.assertRaises(ValueError):
                release_identity("publisher",r)
