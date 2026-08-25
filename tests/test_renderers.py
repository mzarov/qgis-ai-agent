import unittest

from qgis_ai_agent.qgis_tools.common.renderers import renderer_summary
from qgis_ai_agent.qgis_tools.style.renderers import describe_vector_renderer
from qgis_ai_agent.qgis_tools.style.symbols import symbol_info


class Colour:
    def __init__(self, name, valid=True):
        self._name = name
        self._valid = valid

    def name(self):
        return self._name

    def isValid(self):
        return self._valid


class Symbol:
    def __init__(self, kind=2, colour="#cccccc", layers=None):
        self._kind = kind
        self._colour = colour
        self._layers = layers or []

    def type(self):
        return self._kind

    def color(self):
        return Colour(self._colour)

    def symbolLayerCount(self):
        return len(self._layers)

    def symbolLayer(self, index):
        return self._layers[index]


class SymbolLayer:
    def __init__(self, colour, width=None, stroke=None):
        self._colour = colour
        self._width = width
        self._stroke = stroke

    def layerType(self):
        return "SimpleLine"

    def color(self):
        return Colour(self._colour)

    def width(self):
        if self._width is None:
            raise AttributeError
        return self._width

    def strokeColor(self):
        return self._stroke if self._stroke else Colour("#000000", valid=False)

    def strokeWidth(self):
        return 0.4


class Category:
    def value(self):
        return "city"

    def label(self):
        return "Город"

    def symbol(self):
        return Symbol()


class Range:
    def lowerValue(self):
        return 0.0

    def upperValue(self):
        return 100.0

    def label(self):
        return "0 – 100"

    def symbol(self):
        return Symbol()


class Rule:
    def filterExpression(self):
        return '"pop" > 100'

    def label(self):
        return "Крупные"

    def symbol(self):
        return Symbol()


class SingleSymbol:
    def type(self):
        return "singleSymbol"

    def symbol(self):
        return Symbol()


class Categorized(SingleSymbol):
    def type(self):
        return "categorizedSymbol"

    def classAttribute(self):
        return "type"

    def categories(self):
        return [Category(), Category()]


class Graduated(SingleSymbol):
    def type(self):
        return "graduatedSymbol"

    def classAttribute(self):
        return "population"

    def ranges(self):
        return [Range()]


class RuleBased(SingleSymbol):
    def type(self):
        return "RuleRenderer"

    def rootRule(self):
        return self

    def children(self):
        return [Rule()]


class Layer:
    def __init__(self, renderer):
        self._renderer = renderer

    def renderer(self):
        return self._renderer


class DescribeVectorRendererTest(unittest.TestCase):
    def test_single_symbol_does_not_raise(self):
        described = describe_vector_renderer(Layer(SingleSymbol()))
        self.assertEqual(described["type"], "singleSymbol")
        self.assertIn("symbol", described)

    def test_categorized_lists_classes(self):
        described = describe_vector_renderer(Layer(Categorized()))
        self.assertEqual(described["class_attribute"], "type")
        self.assertEqual(described["classes"][0]["value"], "city")

    def test_graduated_lists_ranges(self):
        described = describe_vector_renderer(Layer(Graduated()))
        self.assertEqual(described["classes"][0]["min"], 0.0)
        self.assertEqual(described["classes"][0]["max"], 100.0)

    def test_rule_based_lists_rules(self):
        described = describe_vector_renderer(Layer(RuleBased()))
        self.assertIn('"pop" > 100', described["rules"][0]["filter"])

    def test_broken_renderer_gives_empty_type(self):
        described = describe_vector_renderer(Layer(None))
        self.assertEqual(described["type"], "")


class RendererSummaryTest(unittest.TestCase):
    def test_single_symbol_reads_plainly(self):
        self.assertEqual(renderer_summary(Layer(SingleSymbol())), "одиночный символ")

    def test_categorized_names_field_and_count(self):
        summary = renderer_summary(Layer(Categorized()))
        self.assertIn("«type»", summary)
        self.assertIn("2", summary)

    def test_missing_renderer_gives_nothing(self):
        self.assertEqual(renderer_summary(Layer(None)), "")


class SymbolInfoTest(unittest.TestCase):
    def test_line_without_stroke_omits_it(self):
        symbol = Symbol(kind=1, colour="#ff6011", layers=[SymbolLayer("#ff6011", 1.0)])
        self.assertNotIn("stroke_color", symbol_info(symbol))

    def test_real_stroke_is_kept(self):
        layer = SymbolLayer("#ffffff", 1.0, stroke=Colour("#232323"))
        self.assertEqual(symbol_info(Symbol(layers=[layer]))["stroke_color"], "#232323")

    def test_stacked_layers_are_listed_in_draw_order(self):
        stack = [SymbolLayer("#000000", 1.4), SymbolLayer("#ff6011", 0.8)]
        described = symbol_info(Symbol(kind=1, colour="#ff6011", layers=stack))
        self.assertEqual([entry["color"] for entry in described["layers"]], ["#000000", "#ff6011"])

    def test_symbol_kind_is_named(self):
        self.assertEqual(symbol_info(Symbol(kind=0))["kind"], "точки")


if __name__ == "__main__":
    unittest.main()
