"""Reject ambiguous report JSON before history or digest correlation."""
from hashlib import sha256
import sqlite3
import tempfile
from pathlib import Path
import unittest

from nexus_exchange.cycle_history import BRIEF, CycleHistory, decode, encode, latest

BASE = dict(format='nexus-engagement-brief-v1', finished='2026-11-26T12:00:00+00:00',
            status='Completed', notes=[], sources=[], shortlist=[], jobs={})
RAW = encode(BASE)


class CycleJsonTests(unittest.TestCase):
    def test_duplicate_fields_at_any_depth(self):
        for raw in (RAW.replace(b'"status":', b'"status":"Failed","status":'),
                    RAW.replace(b'"jobs": {}', b'"jobs": {"x":1,"x":2}'),
                    RAW.replace(b'"jobs": {}', b'"jobs": {"x":1,"\\u0078":2}')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_nonfinite_numbers(self):
        for value in (b'NaN', b'Infinity', b'-Infinity', b'1e999', b'-1e999'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode(RAW.replace(b'"notes": []', b'"notes": [' + value + b']'))

    def test_invalid_unicode_in_values_and_keys(self):
        for raw in (RAW.replace(b'"notes": []', b'"notes": ["\\ud800"]'),
                    RAW.replace(b'"jobs": {}', b'"jobs": {"\\udfff": 1}')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_depth_error_normalized(self):
        raw = RAW.replace(b'"notes": []', b'"notes": ' + b'['*2000 + b'0' + b']'*2000)
        with self.assertRaises(ValueError):
            decode(raw)

    def test_both_latest_and_digest_valid_archive_reject_ambiguous_json(self):
        raw = RAW.replace(b'"jobs": {}', b'"jobs": {"x":1,"x":2}')
        digest = sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp, sqlite3.connect(':memory:', isolation_level=None) as db:
            self.addCleanup(db.close)
            directory = Path(tmp)
            (directory / BRIEF).write_bytes(raw)
            with self.assertRaises(ValueError):
                latest(directory)
            history = CycleHistory(db)
            db.execute('INSERT INTO cycle_briefs VALUES (?,?,?,?)',
                       (digest, BASE['finished'], BASE['status'], raw))
            with self.assertRaises(ValueError):
                history.read(digest)

    def test_rejected_new_publication_keeps_prior_and_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp, sqlite3.connect(':memory:', isolation_level=None) as db:
            self.addCleanup(db.close)
            directory = Path(tmp)
            history = CycleHistory(db)
            history.publish(directory, BASE, lambda: None)
            with self.assertRaises(ValueError):
                history.publish(directory, dict(BASE, notes=['\ud800']), lambda: None)
            self.assertEqual((directory / BRIEF).read_bytes(), RAW)
            self.assertEqual(db.execute('SELECT count(*) FROM cycle_briefs').fetchone(), (0,))
            self.assertFalse(list(directory.glob('.cycle-*.tmp')))

    def test_finite_values_unicode_and_legacy_encoding_remain_readable(self):
        brief = dict(BASE, notes=['🌱', 'café', 0.125, {'key': 'value'}])
        self.assertEqual(decode(encode(brief)), brief)
        self.assertEqual(decode(encode(brief).decode('ascii').encode('utf-16')), brief)


if __name__ == '__main__':
    unittest.main()
