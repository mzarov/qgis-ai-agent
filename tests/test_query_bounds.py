import unittest

from qgis_ai_agent.qgis_tools.inspect.queries import run_rows


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
