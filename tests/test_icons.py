import pathlib
import re
import unittest

from qgis_ai_agent.ui import icons

SOURCE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "qgis_ai_agent"
    / "ui"
    / "icons.py"
).read_text(encoding="utf-8")
DOCK = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "qgis_ai_agent"
    / "ui"
    / "dock_widget.py"
).read_text(encoding="utf-8")
COORDINATE = re.compile(r"QPointF\(([0-9.]+), ([0-9.]+)\)")


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


class GeometryTest(unittest.TestCase):
    def test_every_point_stays_inside_the_canvas(self):
        outside = [
            (x, y)
            for x, y in COORDINATE.findall(SOURCE)
            if not (0.0 <= float(x) <= icons.CANVAS and 0.0 <= float(y) <= icons.CANVAS)
        ]
        self.assertEqual(outside, [])

    def test_drawings_actually_draw_something(self):
        for name in ("_draw_clock", "_draw_bin", "_draw_sliders"):
            body = SOURCE.split(f"def {name}(")[1].split("\ndef ")[0]
            self.assertIn("painter.draw", body, name)

    def test_one_stroke_weight_for_the_whole_set(self):
        self.assertEqual(SOURCE.count("pen.setWidthF("), 1)

    def test_brush_is_restored_after_a_filled_knob(self):
        body = SOURCE.split("def _knob(")[1].split("\ndef ")[0]
        self.assertEqual(body.count("setBrush"), 2)
        self.assertIn("NoBrush", body.rsplit("setBrush", 1)[1])


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
