import unittest

from ai_agent.qgis_tools.common import colors
from ai_agent.qgis_tools.style import (
    apply,
    describe_options,
    label_build,
    label_catalogue,
    set_categories,
    set_graduated,
    set_labels,
    set_opacity,
    set_symbol,
    symbol_build,
    symbol_catalogue,
)
from tests.fake_layers import Colour, Field, Layer, Style, Symbol

RAMPS = ["Blues", "Spectral", "Viridis"]


class StyleWriteCase(unittest.TestCase):
    fields = ()
    values = ()

    def setUp(self):
        self.layer = Layer(name="Дороги", fields=self.fields, values=self.values)
        self._colour = colors.QColor
        colors.QColor = Colour
        self._patched = {
            "QgsVectorLayer": apply.QgsVectorLayer,
            "QgsStyle": apply.QgsStyle,
            "QgsSymbol": apply.QgsSymbol,
            "find_layer_by_name": apply.find_layer_by_name,
        }
        apply.QgsVectorLayer = Layer
        apply.QgsStyle = type("StyleHolder", (), {"defaultStyle": staticmethod(lambda: Style(RAMPS))})
        apply.QgsSymbol = type("SymbolHolder", (), {"defaultSymbol": staticmethod(lambda kind: Symbol())})
        apply.find_layer_by_name = self._find

    def tearDown(self):
        colors.QColor = self._colour
        for name, value in self._patched.items():
            setattr(apply, name, value)

    def _find(self, name):
        if name != self.layer.name():
            raise ValueError(f"Слоя «{name}» нет в проекте.")
        return self.layer


class SetSymbolTest(StyleWriteCase):
    def setUp(self):
        super().setUp()
        self.tool = set_symbol.SetSymbolTool()
        self._patched_symbol = (
            set_symbol.QgsSingleSymbolRenderer,
            set_symbol.geometry_type_name,
            symbol_build.base_symbol,
        )
        set_symbol.QgsSingleSymbolRenderer = lambda symbol: ("single", symbol)
        set_symbol.geometry_type_name = lambda layer: "line"
        symbol_build.base_symbol = lambda layer: Symbol()

    def tearDown(self):
        (
            set_symbol.QgsSingleSymbolRenderer,
            set_symbol.geometry_type_name,
            symbol_build.base_symbol,
        ) = self._patched_symbol
        super().tearDown()

    def _apply(self, **properties):
        return self.tool.execute({"layer_name": "Дороги", "properties": properties})

    def test_colour_reaches_the_symbol(self):
        self._apply(color="#1f78b4")
        self.assertEqual(self.layer.renderer_set[1].colour, "#1f78b4")

    def test_renderer_is_replaced_and_layer_redrawn(self):
        self._apply(color="black")
        self.assertEqual(self.layer.renderer_set[0], "single")
        self.assertEqual(self.layer.repaints, 1)

    def test_stroke_lands_on_every_symbol_layer(self):
        result = self._apply(color="white", stroke_color="#232323")
        self.assertEqual(self.layer.renderer_set[1].symbolLayer(0).stroke_color, "#232323")
        self.assertIn("stroke_color", result["applied"])

    def test_inapplicable_property_is_reported_not_swallowed(self):
        result = self._apply(color="black", shape="square")
        self.assertIn("shape", result["skipped"])
        self.assertIn("line", result["skipped_note"])
        self.assertIn("color", result["applied"])

    def test_a_property_never_lands_in_both_lists(self):
        symbol_build.base_symbol = lambda layer: _PartlyDeaf()
        _, outcome = symbol_build.build_symbol(self.layer, {"stroke_color": "white"})
        self.assertEqual(outcome["applied"], ["stroke_color"])
        self.assertEqual(outcome["skipped"], [])

    def test_property_no_layer_accepts_is_skipped(self):
        symbol_build.base_symbol = lambda layer: _PartlyDeaf(accepting=False)
        _, outcome = symbol_build.build_symbol(self.layer, {"stroke_color": "white"})
        self.assertEqual(outcome["skipped"], ["stroke_color"])
        self.assertEqual(outcome["applied"], [])

    def test_nothing_skipped_means_no_note(self):
        self.assertNotIn("skipped_note", self._apply(color="black"))

    def test_bad_colour_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"color": "тёмно-синий"}})
        self.assertIn("#1f78b4", str(caught.exception))

    def test_missing_layer_is_rejected_before_queueing(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Нет такого", "properties": {"color": "black"}})

    def test_out_of_range_width_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"stroke_width": 500}})
        self.assertIn("20", str(caught.exception))

    def test_empty_bag_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {}})
        self.assertIn("describe_style_options", str(caught.exception))

    def test_unknown_property_suggests_a_close_one(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"colour": "black"}})
        self.assertIn("color", str(caught.exception))

    def test_unknown_enum_lists_options(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"stroke_style": "волной"}})
        self.assertIn("dash", str(caught.exception))

    def test_summary_lists_what_changes(self):
        summary = self.tool.summarize_call({"layer_name": "Дороги", "properties": {"color": "black", "size": 2}})
        self.assertIn("color=black", summary)
        self.assertIn("size=2", summary)

    def test_summary_survives_broken_properties(self):
        self.assertTrue(self.tool.summarize_call({"layer_name": "Дороги", "properties": "мусор"}).strip())


class SetCategoriesTest(StyleWriteCase):
    fields = (Field("type"), Field("population", numeric=True))
    values = ("motorway", "primary", "residential")

    def setUp(self):
        super().setUp()
        self.tool = set_categories.SetCategoriesTool()
        self._renderers = (set_categories.QgsCategorizedSymbolRenderer, set_categories.QgsRendererCategory)
        set_categories.QgsCategorizedSymbolRenderer = lambda field, cats: ("categorized", field, cats)
        set_categories.QgsRendererCategory = lambda value, symbol, label: (value, symbol, label)

    def tearDown(self):
        set_categories.QgsCategorizedSymbolRenderer, set_categories.QgsRendererCategory = self._renderers
        super().tearDown()

    def test_one_category_per_unique_value(self):
        result = self.tool.execute({"layer_name": "Дороги", "field": "type", "ramp": "Spectral"})
        self.assertEqual(result["class_count"], 3)
        self.assertEqual(self.layer.renderer_set[1], "type")

    def test_explicit_colours_win_over_ramp(self):
        self.tool.execute(
            {
                "layer_name": "Дороги",
                "field": "type",
                "colors": ["#111111", "#222222", "#333333"],
            }
        )
        used = [category[1].colour for category in self.layer.renderer_set[2]]
        self.assertEqual(used, ["#111111", "#222222", "#333333"])

    def test_unknown_field_suggests_a_close_one(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "typ", "ramp": "Blues"})
        self.assertIn("type", str(caught.exception))

    def test_missing_ramp_falls_back_to_a_default(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "field": "type"})
        self.assertEqual(prepared["field"], "type")
        self.tool.execute(prepared)
        self.assertEqual(len(self.layer.renderer_set[2]), 3)

    def test_unknown_ramp_lists_available(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "type", "ramp": "НетТакой"})
        self.assertIn("Spectral", str(caught.exception))

    def test_colour_count_must_match_categories(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "type", "colors": ["#111111"]})
        self.assertIn("categories", str(caught.exception))

    def test_too_many_categories_points_at_graduated(self):
        self.layer._values = [f"значение {index}" for index in range(80)]
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "type", "ramp": "Blues"})
        self.assertIn("set_graduated", str(caught.exception))


class SetGraduatedTest(StyleWriteCase):
    fields = (Field("population", numeric=True), Field("type"))

    def setUp(self):
        super().setUp()
        self.tool = set_graduated.SetGraduatedTool()
        self.saved_renderer = set_graduated.QgsGraduatedSymbolRenderer
        set_graduated.QgsGraduatedSymbolRenderer = _FakeGraduated

    def tearDown(self):
        set_graduated.QgsGraduatedSymbolRenderer = self.saved_renderer
        super().tearDown()

    def test_default_mode_and_class_count(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "field": "population", "ramp": "Blues"})
        self.assertEqual(prepared["mode"], "quantile")
        self.assertEqual(prepared["classes"], 5)

    def test_text_field_points_at_categories(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "type", "ramp": "Blues"})
        self.assertIn("set_categories", str(caught.exception))

    def test_missing_ramp_falls_back_to_a_default(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "field": "population"})
        self.assertEqual(prepared["classes"], 5)

    def test_class_count_is_bounded(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Дороги", "field": "population", "classes": 99})

    def test_unknown_mode_lists_modes(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "field": "population", "mode": "магия"})
        self.assertIn("jenks", str(caught.exception))

    def test_execute_applies_the_renderer(self):
        result = self.tool.execute({"layer_name": "Дороги", "field": "population", "classes": 4, "ramp": "Viridis"})
        self.assertEqual(result["class_count"], 4)
        self.assertEqual(result["mode"], "quantile")
        self.assertEqual(self.layer.repaints, 1)

    def test_degenerate_data_gives_a_clear_error(self):
        _FakeGraduated.returns_none = True
        try:
            with self.assertRaises(ValueError) as caught:
                self.tool.execute({"layer_name": "Дороги", "field": "population", "ramp": "Blues"})
            self.assertIn("all be equal", str(caught.exception))
        finally:
            _FakeGraduated.returns_none = False


class SetLabelsTest(StyleWriteCase):
    fields = (Field("name"), Field("population", numeric=True))

    def setUp(self):
        super().setUp()
        self.tool = set_labels.SetLabelsTool()
        self._labeling = (
            set_labels.QgsVectorLayerSimpleLabeling,
            label_build.QgsPalLayerSettings,
            label_build.QgsTextFormat,
            label_build.QgsTextBufferSettings,
            label_build.QgsTextShadowSettings,
            label_build.QgsTextBackgroundSettings,
        )
        set_labels.QgsVectorLayerSimpleLabeling = lambda settings: ("simple", settings)
        label_build.QgsPalLayerSettings = _FakeSettings
        label_build.QgsTextFormat = _FakeFormat
        label_build.QgsTextBufferSettings = _FakeSub
        label_build.QgsTextShadowSettings = _FakeSub
        label_build.QgsTextBackgroundSettings = _FakeSub

    def tearDown(self):
        (
            set_labels.QgsVectorLayerSimpleLabeling,
            label_build.QgsPalLayerSettings,
            label_build.QgsTextFormat,
            label_build.QgsTextBufferSettings,
            label_build.QgsTextShadowSettings,
            label_build.QgsTextBackgroundSettings,
        ) = self._labeling
        super().tearDown()

    def _apply(self, **properties):
        self.tool.execute({"layer_name": "Дороги", "properties": {"field": "name", **properties}})
        return self.layer.labeling[1]

    def test_field_reaches_the_settings(self):
        self.assertEqual(self._apply().fieldName, "name")
        self.assertTrue(self.layer.labels_enabled)

    def test_font_family_and_weight(self):
        settings = self._apply(font="Arial", bold=True, italic=True)
        font = settings.text_format.font_object
        self.assertEqual((font.family, font.bold, font.italic), ("Arial", True, True))

    def test_offsets_and_rotation(self):
        settings = self._apply(offset_x=2, offset_y=-3, rotation=45)
        self.assertEqual((settings.xOffset, settings.yOffset, settings.angleOffset), (2.0, -3.0, 45.0))

    def test_placement_is_translated(self):
        self.assertIsNotNone(self._apply(placement="around").placement)

    def test_unknown_placement_lists_options(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"field": "name", "placement": "боком"}})
        self.assertIn("curved", str(caught.exception))

    def test_unknown_property_suggests_a_close_one(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"field": "name", "buffer_colour": "white"}})
        self.assertIn("buffer_color", str(caught.exception))

    def test_out_of_range_number_names_the_limits(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": {"field": "name", "size": 900}})
        self.assertIn("72", str(caught.exception))

    def test_buffer_turns_on_from_its_colour_alone(self):
        buffer = self._apply(buffer_color="white").text_format.buffer
        self.assertTrue(buffer.enabled)
        self.assertEqual(buffer.colour, "white")

    def test_buffer_stays_off_when_not_mentioned(self):
        self.assertFalse(self._apply().text_format.buffer.enabled)

    def test_buffer_can_be_switched_off_explicitly(self):
        buffer = self._apply(buffer_color="white", buffer=False).text_format.buffer
        self.assertFalse(buffer.enabled)

    def test_shadow_and_background_are_independent(self):
        settings = self._apply(shadow_color="grey")
        self.assertTrue(settings.text_format.shadow.enabled)
        self.assertFalse(settings.text_format.background.enabled)

    def test_labels_can_be_turned_off(self):
        prepared = self.tool.prepare({"layer_name": "Дороги", "properties": {"enabled": False}})
        self.tool.execute(prepared)
        self.assertFalse(self.layer.labels_enabled)
        self.assertIsNone(self.layer.labeling)

    def test_turning_on_without_a_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Дороги", "properties": {"size": 12}})

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Дороги", "properties": {"field": "нет_такого"}})

    def test_properties_must_be_an_object(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layer_name": "Дороги", "properties": "field=name"})
        self.assertIn("key-value pairs", str(caught.exception))

    def test_summary_lists_what_changes(self):
        summary = self.tool.summarize_call({"layer_name": "Дороги", "properties": {"field": "name", "bold": True}})
        self.assertIn("field=name", summary)
        self.assertIn("bold=True", summary)

    def test_summary_shortens_a_long_bag(self):
        properties = {"field": "name", "bold": True, "italic": True, "size": 12, "color": "black"}
        self.assertIn("and 1 more", self.tool.summarize_call({"layer_name": "Дороги", "properties": properties}))

    def test_summary_survives_broken_properties(self):
        self.assertTrue(self.tool.summarize_call({"layer_name": "Дороги", "properties": "мусор"}).strip())

    def test_result_reports_what_was_applied(self):
        result = self.tool.execute({"layer_name": "Дороги", "properties": {"field": "name", "bold": True}})
        self.assertEqual(result["applied"], ["bold", "field"])


class CatalogueTest(unittest.TestCase):
    sets = (label_catalogue.LABELS, symbol_catalogue.SYMBOLS)

    def setUp(self):
        self._colour = colors.QColor
        colors.QColor = Colour

    def tearDown(self):
        colors.QColor = self._colour

    def test_describe_matches_the_catalogue(self):
        for kind, known in (("labels", label_catalogue.LABELS), ("symbol", symbol_catalogue.SYMBOLS)):
            described = describe_options.DescribeStyleOptionsTool().execute({"kind": kind})
            self.assertEqual(described["property_count"], len(known.properties), kind)
            self.assertEqual([item["name"] for item in described["properties"]], known.names(), kind)

    def test_unknown_kind_lists_the_kinds(self):
        with self.assertRaises(ValueError) as caught:
            describe_options.DescribeStyleOptionsTool().execute({"kind": "макет"})
        self.assertIn("labels", str(caught.exception))

    def test_every_property_is_documented(self):
        for known in self.sets:
            for item in known.catalogue():
                self.assertTrue(item["description"].strip(), item["name"])

    def test_enum_properties_publish_their_options(self):
        for known in self.sets:
            for prop in known.properties:
                if prop.kind == "enum":
                    self.assertTrue(prop.options, prop.name)

    def test_ranges_are_published_for_numbers(self):
        for known in self.sets:
            for prop in known.properties:
                if prop.kind == "number":
                    self.assertIsNotNone(prop.minimum, prop.name)
                    self.assertIsNotNone(prop.maximum, prop.name)

    def test_names_are_unique_inside_a_set(self):
        for known in self.sets:
            self.assertEqual(len(known.names()), len(set(known.names())), known.subject)

    def test_the_asked_for_properties_exist(self):
        for name in ("font", "color", "offset_x", "offset_y", "placement", "size", "bold"):
            self.assertIn(name, label_catalogue.LABELS.by_name, name)
        for name in ("color", "size", "stroke_color", "stroke_width", "shape", "fill_style"):
            self.assertIn(name, symbol_catalogue.SYMBOLS.by_name, name)

    def test_every_enum_option_maps_to_a_qgis_name(self):
        mappings = {
            "shape": symbol_catalogue.SHAPES,
            "stroke_style": symbol_catalogue.PEN_STYLES,
            "fill_style": symbol_catalogue.BRUSH_STYLES,
            "placement": label_catalogue.PLACEMENTS,
        }
        for known in self.sets:
            for prop in known.properties:
                if prop.kind == "enum":
                    self.assertEqual(set(prop.options), set(mappings[prop.name]), prop.name)

    def test_colour_is_validated_when_coerced(self):
        for known in self.sets:
            colours = [prop for prop in known.properties if prop.kind == "color"]
            self.assertTrue(colours, known.subject)
            with self.assertRaises(ValueError, msg=known.subject):
                known.coerce_all({colours[0].name: "не цвет"})


class SetOpacityTest(StyleWriteCase):
    def setUp(self):
        super().setUp()
        self.tool = set_opacity.SetOpacityTool()
        self.saved_find = set_opacity.find_layer_by_name
        set_opacity.find_layer_by_name = self._find

    def tearDown(self):
        set_opacity.find_layer_by_name = self.saved_find
        super().tearDown()

    def test_fraction_is_applied(self):
        self.tool.execute({"layer_name": "Дороги", "opacity": 0.4})
        self.assertAlmostEqual(self.layer.opacity, 0.4)

    def test_percent_is_understood(self):
        self.tool.execute({"layer_name": "Дороги", "opacity": 60})
        self.assertAlmostEqual(self.layer.opacity, 0.6)

    def test_out_of_range_is_clamped(self):
        self.tool.execute({"layer_name": "Дороги", "opacity": 300})
        self.assertAlmostEqual(self.layer.opacity, 1.0)

    def test_garbage_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_name": "Дороги", "opacity": "прозрачно"})

    def test_summary_never_throws_on_empty_params(self):
        self.assertTrue(self.tool.summarize_call({}).strip())


class _FakeGraduated:
    returns_none = False
    EqualInterval = 0
    Quantile = 1
    Jenks = 2
    Pretty = 3
    StdDev = 4

    def __init__(self, classes):
        self._classes = classes

    def ranges(self):
        return list(range(self._classes))

    @staticmethod
    def createRenderer(layer, field, classes, mode, symbol, ramp):
        if _FakeGraduated.returns_none:
            return None
        return _FakeGraduated(classes)


class _Deaf:
    pass


class _Hearing:
    def setStrokeColor(self, value):
        self.value = value


class _PartlyDeaf:
    def __init__(self, accepting=True):
        self._layers = [_Hearing() if accepting else _Deaf(), _Deaf()]

    def symbolLayerCount(self):
        return len(self._layers)

    def symbolLayer(self, index):
        return self._layers[index]


class _FakeFont:
    def __init__(self):
        self.family = None
        self.bold = None
        self.italic = None

    def setFamily(self, value):
        self.family = value

    def setBold(self, value):
        self.bold = value

    def setItalic(self, value):
        self.italic = value


class _FakeSub:
    def __init__(self):
        self.enabled = None
        self.size = None
        self.colour = None

    def setEnabled(self, value):
        self.enabled = value

    def setSize(self, value):
        self.size = value

    def setColor(self, value):
        self.colour = value.name()

    def setFillColor(self, value):
        self.colour = value.name()


class _FakeFormat:
    def __init__(self):
        self.size = None
        self.colour = None
        self.opacity = None
        self.buffer = None
        self.shadow = None
        self.background = None
        self.font_object = _FakeFont()

    def font(self):
        return self.font_object

    def setFont(self, value):
        self.font_object = value

    def setSize(self, value):
        self.size = value

    def setColor(self, value):
        self.colour = value.name()

    def setOpacity(self, value):
        self.opacity = value

    def setBuffer(self, value):
        self.buffer = value

    def setShadow(self, value):
        self.shadow = value

    def setBackground(self, value):
        self.background = value


class _FakeSettings:
    def __init__(self):
        self.fieldName = ""
        self.isExpression = False
        self.offsetUnits = None
        self.distUnits = None
        self.xOffset = None
        self.yOffset = None
        self.dist = None
        self.angleOffset = None
        self.placement = None
        self.text_format = None

    def setFormat(self, text_format):
        self.text_format = text_format


if __name__ == "__main__":
    unittest.main()
