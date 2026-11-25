import unittest
from nexus_exchange.scout_requirements_form import declaration_from_fields


def fields(**updates):
    raw = dict(capability_id="csv_preserve_and_standardize_v2", input_format="UTF8_CSV",
               input_bytes="200", max_cell_chars="30", preserve_all_fields="Yes",
               requires_deduplication="No", requires_inference="No", requires_formulas="No",
               input_sha256="a" * 64, columns="id,name", key_column="id", expected_rows="2",
               right_input_bytes="", right_input_sha256="", right_expected_rows="")
    raw.update(updates)
    return raw


class ScoutRequirementsFormTests(unittest.TestCase):
    def test_csv_declaration_has_exact_backend_shape(self):
        result = declaration_from_fields(fields())
        self.assertEqual(result, dict(capability_id="csv_preserve_and_standardize_v2",
            input_format="UTF8_CSV", input_bytes=200, max_cell_chars=30,
            preserve_all_fields=True, requires_deduplication=False, requires_inference=False,
            requires_formulas=False, specification=dict(input_sha256="a"*64,
                columns=["id", "name"], key_column="id", expected_rows=2)))

    def test_unknown_sizes_and_absent_schema_are_not_inferred(self):
        result = declaration_from_fields(fields(input_bytes="", max_cell_chars="",
            input_sha256="", columns="", key_column="", expected_rows=""))
        self.assertIsNone(result["input_bytes"])
        self.assertIsNone(result["max_cell_chars"])
        self.assertIsNone(result["specification"])

    def test_explicit_flags_and_bounded_numbers(self):
        for updates in ({"requires_formulas":""}, {"preserve_all_fields":"Maybe"},
                        {"input_bytes":"-1"}, {"input_bytes":"1e3"},
                        {"input_bytes":"99999999999"}, {"input_bytes":"１２"}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                declaration_from_fields(fields(**updates))

    def test_partial_schema_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            declaration_from_fields(fields(input_sha256=""))

    def test_reconciliation_keeps_both_inputs_and_rejects_hidden_fields(self):
        result = declaration_from_fields(fields(capability_id="csv_key_reconciliation_v1",
            preserve_all_fields="No", right_input_bytes="300", right_input_sha256="b"*64,
            right_expected_rows="3"))
        self.assertEqual(result["right_input_bytes"], 300)
        self.assertEqual(result["specification"]["right_input_sha256"], "b"*64)
        self.assertEqual(result["specification"]["right_expected_rows"], 3)
        with self.assertRaises(ValueError):
            declaration_from_fields(fields(right_input_bytes="300"))

    def test_unknown_fields_and_oversized_text_rejected(self):
        for updates in ({"external_authority":"Yes"}, {"columns":"a"*2049}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                declaration_from_fields(fields(**updates))
