import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus_exchange.followup_export import write_reviewed_text, MAX_EXPORT_BYTES

BODY = 'LOCAL FOLLOW-UP DRAFT — DO NOT SEND\nSynthetic review only.\n'


class FollowupExportTests(unittest.TestCase):
    def test_exact_bytes_and_no_overwrite(self):
        with TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'draft.txt'
            data = BODY.encode('utf-8')
            ref = write_reviewed_text(path, BODY, permit=lambda: None)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(ref, f'sha256:{hashlib.sha256(data).hexdigest()};bytes:{len(data)}')
            with self.assertRaises(FileExistsError):
                write_reviewed_text(path, BODY, permit=lambda: None)
            self.assertEqual(path.read_bytes(), data)

    def test_invalid_path_body_and_budget(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for path, body in [('relative.txt', BODY), (root / 'draft.eml', BODY),
                               (root / 'draft.txt', 'not a reviewed draft'),
                               (root / 'draft.txt', BODY + 'x' * MAX_EXPORT_BYTES)]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    write_reviewed_text(path, body, permit=lambda: None)
            self.assertEqual(list(root.iterdir()), [])

    def test_halt_before_creation(self):
        with TemporaryDirectory() as temp:
            path = Path(temp).resolve() / 'draft.txt'
            calls = 0
            def permit():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise PermissionError('halted')
            with self.assertRaises(PermissionError):
                write_reviewed_text(path, BODY, permit=permit)
            self.assertFalse(path.exists())
