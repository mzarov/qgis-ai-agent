import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "src")

import qgis_stub

from qgis_ai_agent.qgis_tools.style.renderers import describe_vector_renderer


class Colour:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def isValid(self):
        return True


class Symbol:
    def type(self):
        return 2

    def color(self):
        return Colour("#cccccc")

    def symbolLayerCount(self):
        return 1

    def symbolLayer(self, index):
        raise AttributeError


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
        return "\"pop\" > 100"

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
        return [Category()]


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


EXPECTED = {
    "singleSymbol": "symbol",
    "categorizedSymbol": "classes",
    "graduatedSymbol": "classes",
    "RuleRenderer": "rules",
}

failures = []
for renderer in (SingleSymbol(), Categorized(), Graduated(), RuleBased()):
    kind = renderer.type()
    try:
        described = describe_vector_renderer(Layer(renderer))
    except Exception as err:
        failures.append(f"{kind}: {type(err).__name__}: {err}")
        continue
    key = EXPECTED[kind]
    if key not in described:
        failures.append(f"{kind}: в ответе нет ключа {key}: {described}")
    else:
        print(f"  {kind:<20} {key} -> {described[key]}")

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("все четыре типа рендерера разбираются")
