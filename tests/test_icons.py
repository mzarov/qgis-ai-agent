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


GLYPHS = pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "glyphs"
SVG_ART = (pathlib.Path(__file__).resolve().parent.parent / "ai_agent" / "ui" / "svg_art.py").read_text(
    encoding="utf-8"
)


class GlyphSetTest(unittest.TestCase):
    def test_every_role_has_its_outline_file(self):
        for role, name in icons.NAMES.items():
            self.assertTrue((GLYPHS / f"{name}.svg").is_file(), role)

    def test_the_set_is_one_family_with_one_stroke(self):
        for path in GLYPHS.glob("*.svg"):
            root = ElementTree.parse(path).getroot()
            self.assertEqual(root.attrib["viewBox"], "0 0 24 24", path.name)
            self.assertEqual(root.attrib["stroke-width"], "1.75", path.name)
            self.assertEqual(root.attrib["fill"], "none", path.name)

    def test_every_file_carries_the_lucide_licence(self):
        for path in GLYPHS.glob("*.svg"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("ISC License", text, path.name)
            self.assertIn("Lucide Icons and Contributors", text, path.name)

    def test_artwork_is_black_so_it_can_be_recoloured(self):
        for path in GLYPHS.glob("*.svg"):
            self.assertNotIn("currentColor", path.read_text(encoding="utf-8"), path.name)

    def test_recolouring_keeps_the_shape_and_replaces_the_ink(self):
        self.assertIn("CompositionMode_SourceIn", SVG_ART)

    def test_the_device_ratio_sizes_the_pixmap_not_the_drawing(self):
        self.assertIn("image.setDevicePixelRatio(ratio)", SVG_ART)
        self.assertIn("QRectF(0, 0, size, size)", SVG_ART)


if __name__ == "__main__":
    unittest.main()
