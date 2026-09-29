import unittest
from unittest.mock import patch

from ai_agent.qgis_tools.inspect import queries
from ai_agent.qgis_tools.inspect.queries import run_aggregate, run_rows


class _Fields:
    @staticmethod
    def names():
        return ["value", "unused"]


class _Feature:
    def __init__(self, value):
        self._value = value

    def attributes(self):
        return [self._value, "large"]


class _Request:
    def __init__(self):
        self.limit = None
        self.subset = None

    def setLimit(self, value):
        self.limit = value
        return self

    def setSubsetOfAttributes(self, indexes, fields):
        self.subset = list(indexes)
        return self


class _Layer:
    def __init__(self, size=100_000):
        self.size = size
        self.read = 0

    @staticmethod
    def fields():
        return _Fields()

    def getFeatures(self, request):
        count = min(self.size, request.limit or self.size)
        for value in range(count):
            self.read += 1
            yield _Feature(value)


class QueryBoundsTest(unittest.TestCase):
    def test_unordered_rows_only_read_limit_plus_one(self):
        layer = _Layer()
        request = _Request()
        result = run_rows(layer, request, object(), {"limit": 20, "fields": ["value"]})
        self.assertEqual(layer.read, 21)
        self.assertEqual(result["shown"], 20)
        self.assertTrue(result["has_more"])
        self.assertTrue(result["matched_is_lower_bound"])

    def test_requested_attributes_are_pushed_to_the_provider(self):
        request = _Request()
        run_rows(_Layer(size=1), request, object(), {"fields": ["value"]})
        self.assertEqual(request.subset, [0])


if __name__ == "__main__":
    unittest.main()


class _AggregatingLayer(_Layer):
    """A remote-looking layer whose native aggregate answers are recorded."""

    def __init__(self, answers, provider="postgres", count=250_000):
        super().__init__(size=count)
        self.answers = dict(answers)
        self.calls = []
        self.provider = provider
        self.count = count

    def providerType(self):
        return self.provider

    def featureCount(self):
        return self.count

    def selectedFeatureIds(self):
        return [4, 5]

    def aggregate(self, kind, expression, parameters, context, fids=None):
        self.calls.append((kind, expression, getattr(parameters, "filter", ""), fids))
        return self.answers.get(expression, (None, False))

    def getFeatures(self, request):
        raise AssertionError("a native aggregate must not scan features in Python")


class _Parameters:
    filter = ""


class NativeAggregateTest(unittest.TestCase):
    def setUp(self):
        replacement = patch.object(queries, "prepared", lambda text, label, context, layer=None: text)
        replacement.start()
        self.addCleanup(replacement.stop)
        replacement = patch.object(queries.QgsAggregateCalculator, "AggregateParameters", _Parameters)
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_a_bare_count_on_a_local_layer_uses_the_cheap_count(self):
        layer = _AggregatingLayer({}, provider="ogr", count=12)
        result = run_aggregate(layer, _Request(), None, {}, "count")
        self.assertEqual((result["matched"], result["value"]), (12, 12))
        self.assertEqual(layer.calls, [])

    def test_a_filtered_sum_runs_natively_past_the_python_scan_limit(self):
        layer = _AggregatingLayer({"1": (float(queries.MAX_SCAN + 10), True), "population": (1234.56789, True)})
        params = {"filter": "kind = 'city'", "expression": "population"}
        result = run_aggregate(layer, _Request(), None, params, "sum")
        self.assertEqual(result["matched"], queries.MAX_SCAN + 10)
        self.assertEqual(result["value"], 1234.5679)
        self.assertEqual([call[1:3] for call in layer.calls], [("1", "kind = 'city'"), ("population", "kind = 'city'")])

    def test_selected_only_passes_the_selected_ids(self):
        layer = _AggregatingLayer({"1": (2.0, True), "$area": (10.0, True)})
        result = run_aggregate(layer, _Request(), None, {"selected_only": True, "expression": "$area"}, "max")
        self.assertEqual((result["matched"], result["value"]), (2, 10.0))
        self.assertTrue(all(call[3] == [4, 5] for call in layer.calls))

    def test_a_refused_native_aggregate_falls_back_to_the_scan(self):
        layer = _AggregatingLayer({"1": (3.0, True)}, count=3)
        layer.getFeatures = _Layer(size=3).getFeatures
        with (
            patch.object(queries, "evaluate", lambda expression, context, feature: "text"),
            self.assertRaisesRegex(ValueError, "numbers only"),
        ):
            run_aggregate(layer, _Request(), None, {"expression": "name"}, "sum")

    def test_no_match_keeps_the_empty_answer(self):
        layer = _AggregatingLayer({"1": (0.0, True)})
        result = run_aggregate(layer, _Request(), None, {"filter": "false", "expression": "n"}, "sum")
        self.assertEqual((result["matched"], result["value"]), (0, None))
