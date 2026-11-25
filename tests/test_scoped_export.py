import unittest
from nexus_exchange.scoped_export import checked_export_pins, require_matching_pins


def pins():
    return dict(expected_contract='a'*64, expected_report='b'*64,
                expected_artifact='c'*64)


class ScopedExportTests(unittest.TestCase):
    def test_exact_pins_return_detached_copy(self):
        original=pins()
        checked=checked_export_pins(original)
        self.assertEqual(checked,original)
        checked['expected_report']='d'*64
        self.assertEqual(original['expected_report'],'b'*64)

    def test_invalid_shape_or_hash_is_rejected(self):
        for bad in (None,{},dict(pins(),external_authority=True),
                    dict(pins(),expected_contract='A'*64),
                    dict(pins(),expected_artifact='c'*63),
                    dict(pins(),expected_report=1),
                    dict(pins(),expected_report='g'*64)):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                checked_export_pins(bad)

    def test_every_pin_must_match(self):
        self.assertEqual(require_matching_pins(pins(),pins()),pins())
        for key in pins():
            with self.subTest(key=key),self.assertRaises(ValueError):
                require_matching_pins(pins(),dict(pins(),**{key:'d'*64}))

    def test_invalid_actual_shape_cannot_match(self):
        with self.assertRaises(ValueError):
            require_matching_pins(pins(),dict(pins(),exported=True))
