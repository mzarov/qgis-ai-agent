import unittest

from qgis_ai_agent.qgis_tools.inspect.aggregates import AGGREGATE_FUNCTIONS, compute


class ComputeTest(unittest.TestCase):
    def test_count_uses_matched_not_values(self):
        self.assertEqual(compute("count", [None, 1, 2], 7), 7)

    def test_sum_skips_empty(self):
        self.assertEqual(compute("sum", [10, None, 20], 3), 30.0)

    def test_mean(self):
        self.assertEqual(compute("mean", [1, 2, 3], 3), 2.0)

    def test_median(self):
        self.assertEqual(compute("median", [1, 100, 2], 3), 2.0)

    def test_min_and_max(self):
        self.assertEqual(compute("min", [5, 1, 9], 3), 1.0)
        self.assertEqual(compute("max", [5, 1, 9], 3), 9.0)

    def test_stdev(self):
        self.assertAlmostEqual(compute("stdev", [2, 4, 4, 4, 5, 5, 7, 9], 8), 2.1381, places=3)

    def test_stdev_needs_two_values(self):
        self.assertIsNone(compute("stdev", [7], 1))

    def test_count_distinct_ignores_empty(self):
        self.assertEqual(compute("count_distinct", ["a", "b", "a", None], 4), 2)

    def test_all_empty_gives_none(self):
        self.assertIsNone(compute("mean", [None, None], 2))

    def test_concatenate_joins(self):
        self.assertEqual(compute("concatenate", ["a", "b"], 2), "a, b")

    def test_concatenate_truncates(self):
        result = compute("concatenate", [str(index) for index in range(80)], 80)
        self.assertIn("всего 80", result)

    def test_text_in_numeric_aggregate_explains(self):
        with self.assertRaises(ValueError) as caught:
            compute("sum", ["текст"], 1)
        self.assertIn("только с числами", str(caught.exception))

    def test_unknown_function_lists_available(self):
        with self.assertRaises(ValueError) as caught:
            compute("медиана", [1], 1)
        self.assertIn("count", str(caught.exception))

    def test_every_advertised_function_is_callable(self):
        for name in AGGREGATE_FUNCTIONS:
            compute(name, [1, 2], 2)


if __name__ == "__main__":
    unittest.main()
