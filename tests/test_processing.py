import unittest

from qgis_ai_agent.qgis_tools.processing.utils import _coerce_enum_value


class CoerceEnumTest(unittest.TestCase):
    OPTIONS = ["Round", "Flat", "Square"]

    def test_label_becomes_index(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "Round"), 0)

    def test_label_is_case_insensitive(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "flat"), 1)
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "SQUARE"), 2)

    def test_index_is_kept(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, 2), 2)

    def test_numeric_string_becomes_index(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "1"), 1)

    def test_unknown_label_passes_through(self):
        self.assertEqual(_coerce_enum_value(self.OPTIONS, "Нет такого"), "Нет такого")

    def test_bool_is_not_treated_as_index(self):
        self.assertIs(_coerce_enum_value(self.OPTIONS, True), True)


if __name__ == "__main__":
    unittest.main()
