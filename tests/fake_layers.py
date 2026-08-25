HEX_DIGITS = "0123456789abcdefABCDEF"
NAMED_COLOURS = {"steelblue", "black", "white", "red", "blue", "green", "grey", "gray"}


class Colour:
    def __init__(self, value=""):
        self._value = str(value or "").strip()

    def isValid(self):
        if self._value.lower() in NAMED_COLOURS:
            return True
        if not self._value.startswith("#") or len(self._value) not in (7, 9):
            return False
        return all(char in HEX_DIGITS for char in self._value[1:])

    def name(self):
        return self._value.lower()


class Ramp:
    def __init__(self, name):
        self._name = name

    def color(self, position):
        return Colour(f"#{int(position * 255):02x}0000")


class Style:
    def __init__(self, ramps):
        self._ramps = list(ramps)

    def colorRampNames(self):
        return list(self._ramps)

    def colorRamp(self, name):
        return Ramp(name)


class Field:
    def __init__(self, name, numeric=False):
        self._name = name
        self._numeric = numeric

    def name(self):
        return self._name

    def isNumeric(self):
        return self._numeric


class Fields:
    def __init__(self, fields):
        self._fields = list(fields)

    def __iter__(self):
        return iter(self._fields)

    def indexFromName(self, name):
        for index, field in enumerate(self._fields):
            if field.name() == name:
                return index
        return -1

    def at(self, index):
        return self._fields[index]


class SymbolLayer:
    def __init__(self):
        self.stroke_color = None
        self.stroke_width = None

    def setStrokeColor(self, colour):
        self.stroke_color = colour.name()

    def setStrokeWidth(self, width):
        self.stroke_width = width


class Symbol:
    def __init__(self, layers=1):
        self.colour = None
        self.size = None
        self._layers = [SymbolLayer() for _ in range(layers)]

    def setColor(self, colour):
        self.colour = colour.name()

    def setWidth(self, value):
        self.size = value

    def symbolLayerCount(self):
        return len(self._layers)

    def symbolLayer(self, index):
        return self._layers[index]


class Layer:
    def __init__(self, name="Слой", fields=(), values=(), geometry=1):
        self._name = name
        self._fields = Fields(fields)
        self._values = list(values)
        self._geometry = geometry
        self.renderer_set = None
        self.opacity = None
        self.labeling = None
        self.labels_enabled = None
        self.repaints = 0

    def name(self):
        return self._name

    def id(self):
        return f"{self._name}_id"

    def fields(self):
        return self._fields

    def geometryType(self):
        return self._geometry

    def uniqueValues(self, index):
        return set(self._values)

    def setRenderer(self, renderer):
        self.renderer_set = renderer

    def setOpacity(self, value):
        self.opacity = value

    def setLabeling(self, labeling):
        self.labeling = labeling

    def setLabelsEnabled(self, enabled):
        self.labels_enabled = enabled

    def triggerRepaint(self):
        self.repaints += 1
