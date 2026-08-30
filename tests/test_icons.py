import pathlib
import re
import unittest
import xml.etree.ElementTree as ElementTree

from ai_agent.ui import icons

SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "icons.py").read_text(encoding="utf-8")
DOCK = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "dock_widget.py").read_text(
    encoding="utf-8"
)
COORDINATE = re.compile(r"QPointF\(([0-9.]+), ([0-9.]+)\)")
PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "plugin.py"
BRAND_ICON = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "icon.svg"
RENDERED_ICON = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "icon.png"


class ApiTest(unittest.TestCase):
    def test_header_has_an_icon_for_every_button(self):
        for name in ("sessions", "clear", "settings"):
            self.assertTrue(callable(getattr(icons, name)), name)

    def test_dock_uses_the_drawn_set(self):
        for name in ("icons.sessions", "icons.clear", "icons.settings"):
            self.assertIn(name, DOCK)

    def test_dock_no_longer_names_qgis_theme_icons(self):
        self.assertNotIn(".svg", DOCK)

    def test_glyph_fallback_survives(self):
        self.assertIn("button.setText(glyph)", DOCK)
        self.assertIn("except Exception:", DOCK)

    def test_toolbar_icon_is_loaded_from_the_package_root(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn('ICON_FILENAME = "icon.png"', source)
        self.assertIn("os.path.dirname(os.path.abspath(__file__))", source)
        self.assertNotIn('"..", "..", ".."', source)

    def test_brand_icon_is_valid_svg(self):
        root = ElementTree.parse(BRAND_ICON).getroot()
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.attrib["viewBox"], "0 0 128 128")

    def test_published_icon_is_a_128_pixel_png(self):
        data = RENDERED_ICON.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(data[16:20], "big"), 128)
        self.assertEqual(int.from_bytes(data[20:24], "big"), 128)


class GeometryTest(unittest.TestCase):
    def test_every_point_stays_inside_the_canvas(self):
        outside = [
            (x, y)
            for x, y in COORDINATE.findall(SOURCE)
            if not (0.0 <= float(x) <= icons.CANVAS and 0.0 <= float(y) <= icons.CANVAS)
        ]
        self.assertEqual(outside, [])

    def test_drawings_actually_draw_something(self):
        for name in ("_draw_clock", "_draw_bin", "_draw_gear"):
            body = SOURCE.split(f"def {name}(")[1].split("\ndef ")[0]
            self.assertIn("painter.draw", body, name)

    def test_one_stroke_weight_for_the_whole_set(self):
        self.assertEqual(SOURCE.count("pen.setWidthF("), 1)

    def test_the_whole_set_is_stroked_never_filled(self):
        self.assertEqual(SOURCE.count("setBrush"), 1)
        self.assertIn("painter.setBrush(Qt.BrushStyle.NoBrush)", SOURCE)

    def test_gear_fits_the_canvas(self):
        reach = icons.GEAR_RING + icons.GEAR_TOOTH
        self.assertGreater(icons.CENTRE - reach, 0.0)
        self.assertLess(icons.CENTRE + reach, icons.CANVAS)

    def test_gear_hub_sits_inside_its_ring(self):
        self.assertLess(icons.GEAR_HUB, icons.GEAR_RING)

    def test_every_tooth_stays_inside_the_canvas(self):
        outer = icons.GEAR_RING + icons.GEAR_TOOTH
        for index in range(icons.GEAR_TEETH):
            for value in icons.tooth_at(index, outer):
                self.assertGreaterEqual(round(value, 6), 0.0, index)
                self.assertLessEqual(round(value, 6), icons.CANVAS, index)

    def test_teeth_are_distinguishable_at_header_size(self):
        self.assertGreater(icons.tooth_gap(15), 3.0)

    def test_teeth_are_evenly_spaced(self):
        outer = icons.GEAR_RING + icons.GEAR_TOOTH
        first = icons.tooth_at(0, outer)
        self.assertAlmostEqual(first[0], icons.CENTRE + outer)
        self.assertAlmostEqual(first[1], icons.CENTRE)
        quarter = icons.tooth_at(icons.GEAR_TEETH // 4, outer)
        self.assertAlmostEqual(quarter[0], icons.CENTRE)

    def test_teeth_start_where_the_ring_ends(self):
        body = SOURCE.split("def _draw_gear(")[1].split("\ndef ")[0]
        self.assertIn("_at(index, GEAR_RING), _at(index, GEAR_RING + GEAR_TOOTH)", body)

    def test_tooth_maths_has_no_qt_in_it(self):
        body = SOURCE.split("def tooth_at(")[1].split("\ndef ")[0]
        self.assertNotIn("QPointF", body)


class ScaleTest(unittest.TestCase):
    def test_canvas_maps_exactly_onto_the_icon(self):
        for size in (12, 15, 16, 24, 32):
            self.assertAlmostEqual(icons.scale_for(size) * icons.CANVAS, size, msg=str(size))

    def test_scale_ignores_the_device_ratio(self):
        body = SOURCE.split("def scale_for(")[1].split("\ndef ")[0]
        self.assertNotIn("ratio", body)

    def test_painter_scales_by_that_factor_only(self):
        body = SOURCE.split("def _icon(")[1].split("\ndef ")[0]
        self.assertIn("painter.scale(scale_for(size), scale_for(size))", body)
        self.assertNotIn("size * ratio / CANVAS", body)

    def test_ratio_is_used_for_the_pixmap_not_the_transform(self):
        body = SOURCE.split("def _icon(")[1].split("\ndef ")[0]
        self.assertIn("QPixmap(int(size * ratio), int(size * ratio))", body)
        self.assertIn("setDevicePixelRatio(ratio)", body)


class RatioTest(unittest.TestCase):
    def test_absent_screen_falls_back_to_one(self):
        saved = icons.QGuiApplication
        icons.QGuiApplication = None
        try:
            self.assertEqual(icons._ratio(), 1.0)
        finally:
            icons.QGuiApplication = saved

    def test_absurd_ratio_is_ignored(self):
        self.assertGreater(icons.MAX_RATIO, 1.0)
        body = SOURCE.split("def _ratio(")[1]
        self.assertIn("MAX_RATIO", body)
        self.assertIn("return 1.0", body)


if __name__ == "__main__":
    unittest.main()
