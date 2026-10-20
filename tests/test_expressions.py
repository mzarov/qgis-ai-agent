import unittest
from unittest import mock

from ai_agent.qgis_tools.common import expressions as expressions_module
from ai_agent.qgis_tools.common.expressions import (
    ALL_ATTRIBUTES,
    check_columns,
    compile_expression,
    parse_order_by,
    sort_key,
)


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


class Referencing:
    def __init__(self, *columns):
        self._columns = set(columns)

    def referencedColumns(self):
        return set(self._columns)


class Fields:
    def names(self):
        return ["name", "pop2020"]


class Layer:
    def fields(self):
        return Fields()


class CheckColumnsTest(unittest.TestCase):
    def test_an_aggregate_over_another_layer_is_not_refused(self):
        check_columns(Referencing("name", ALL_ATTRIBUTES), Layer(), "expression", "aggregate(...)")

    def test_an_unknown_field_is_refused_with_the_text_value_hint(self):
        with self.assertRaisesRegex(ValueError, "popul.*single quotes"):
            check_columns(Referencing("popul"), Layer(), "filter", '"popul" > 5')

    def test_an_expression_in_double_quotes_is_told_to_drop_them(self):
        with self.assertRaisesRegex(ValueError, "without quotes.*geometry\\(@parent\\)"):
            check_columns(Referencing("within($geometry, @geometry)"), Layer(), "expression", "aggregate(...)")


class Parsed:
    KNOWN = ("decode_uri", "env", "eval", "layer_property", "load_layer", "sqlite_fetch_and_increment", "upper")

    def __init__(self, text):
        self._text = text

    def hasParserError(self):
        return False

    def referencedFunctions(self):
        return {name for name in self.KNOWN if f"{name}(" in self._text}

    def referencedColumns(self):
        return set()


class UnsafeFunctionTest(unittest.TestCase):
    def test_functions_that_write_read_secrets_or_run_text_are_refused(self):
        with mock.patch.object(expressions_module, "QgsExpression", Parsed):
            for text in (
                "sqlite_fetch_and_increment('/tmp/x.gpkg', 't', 'id', 'n', 'a', map()) > 0",
                "upper(env('HOME'))",
                "eval('1 + 1')",
                "load_layer('/tmp/x.shp', 'ogr') IS NULL",
                "layer_property(@layer, 'source')",
                "decode_uri(@layer, 'path')",
            ):
                with self.subTest(text=text), self.assertRaisesRegex(ValueError, r"\(\) is not allowed in 'filter'"):
                    compile_expression(text, "filter")
            compile_expression("upper(\"name\") = 'A'", "filter")
