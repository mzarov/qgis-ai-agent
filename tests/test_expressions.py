import unittest

from ai_agent.qgis_tools.common.expressions import parse_order_by, sort_key


class ParseOrderByTest(unittest.TestCase):
    def test_descending(self):
        self.assertEqual(parse_order_by("population DESC"), ("population", False))

    def test_ascending_is_default(self):
        self.assertEqual(parse_order_by("population"), ("population", True))

    def test_lowercase_direction(self):
        self.assertEqual(parse_order_by("$length desc"), ("$length", False))

    def test_explicit_asc(self):
        self.assertEqual(parse_order_by("name ASC"), ("name", True))

    def test_quoted_name_with_space_is_kept(self):
        self.assertEqual(parse_order_by('"поле с пробелом"'), ('"поле с пробелом"', True))

    def test_empty(self):
        self.assertEqual(parse_order_by(""), ("", True))


class SortKeyTest(unittest.TestCase):
    def test_mixed_types_do_not_raise(self):
        sorted([100, None, "текст", 5.5, True], key=sort_key)

    def test_none_sorts_last(self):
        self.assertIsNone(sorted([100, None, "т"], key=sort_key)[-1])

    def test_numbers_before_strings(self):
        self.assertEqual(sorted(["b", 2, "a", 1], key=sort_key)[:2], [1, 2])

    def test_numeric_order_is_numeric(self):
        self.assertEqual(sorted([10, 9, 100], key=sort_key), [9, 10, 100])


if __name__ == "__main__":
    unittest.main()
