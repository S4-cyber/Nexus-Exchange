import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_pins(text):
    pins = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([a-z][a-z0-9-]*)==([0-9]+(?:\.[0-9]+)+)', line)
        if not match or match[1] in pins:
            raise ValueError('invalid or duplicate build pin')
        pins[match[1]] = match[2]
    if not pins:
        raise ValueError('empty build pin inventory')
    return pins


class BuildPinTests(unittest.TestCase):
    def test_rejects_unpinned_duplicate_or_direct_requirements(self):
        for text in ('', 'foo>=1.0', 'foo==1.0\nfoo==2.0', 'foo @ https://example.invalid/x', '-r other.txt'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_pins(text)

    def test_reviewed_windows_lock(self):
        pins = parse_pins((ROOT / 'requirements-build-windows.txt').read_text(encoding='utf-8'))
        self.assertEqual(pins, {'altgraph':'0.17.5','packaging':'26.3','pefile':'2023.2.7','pyinstaller':'6.12.0','pyinstaller-hooks-contrib':'2026.10','pywin32-ctypes':'0.2.3','setuptools':'84.2.1'})
