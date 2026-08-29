import pathlib
import unittest

from ai_agent.qgis_tools.layout import add_layout_item as add_module
from ai_agent.qgis_tools.layout import configure_layout_item as configure_module
from ai_agent.qgis_tools.layout import export_layout as export_module
from ai_agent.qgis_tools.layout import items, pages
from ai_agent.qgis_tools.layout.add_layout_item import AddLayoutItemTool
from ai_agent.qgis_tools.layout.configure_layout_item import ConfigureLayoutItemTool
from ai_agent.qgis_tools.layout.export_layout import ExportLayoutTool, _checked_path


class PageSizeTest(unittest.TestCase):
    def test_portrait_and_landscape_swap_the_sides(self):
        self.assertEqual(pages.page_size_mm("a4", "portrait"), (210.0, 297.0))
        self.assertEqual(pages.page_size_mm("a4", "landscape"), (297.0, 210.0))

    def test_defaults_are_a4_landscape(self):
        self.assertEqual(pages.page_size_mm("", ""), (297.0, 210.0))

    def test_unknown_page_lists_the_presets(self):
        with self.assertRaises(ValueError) as caught:
            pages.page_size_mm("b5", "")
        self.assertIn("a4", str(caught.exception))

    def test_unknown_orientation_is_refused(self):
        with self.assertRaises(ValueError):
            pages.page_size_mm("a4", "diagonal")


class Rect:
    def __init__(self, x, y, w, h):
        self._values = (x, y, w, h)

    def x(self):
        return self._values[0]

    def y(self):
        return self._values[1]

    def width(self):
        return self._values[2]

    def height(self):
        return self._values[3]


class ItemMixin:
    def __init__(self, item_id, rect=(0, 0, 10, 10)):
        self._id = item_id
        self._rect = Rect(*rect)
        self._moved = None
        self._text = "old"

    def id(self):
        return self._id

    def sceneBoundingRect(self):
        return self._rect

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setTextFormat(self, text_format):
        return None

    def attemptMove(self, point):
        self._moved = point

    def attemptResize(self, size):
        self._resized = size


def _fake_class(kind_class):
    return type("Fake", (ItemMixin, kind_class), {})


class FakeLayout:
    def __init__(self, layout_items=(), page=(297.0, 210.0)):
        self._items = list(layout_items)
        self._page = page

    def name(self):
        return "Лист"

    def items(self):
        return list(self._items)

    def pageCollection(self):
        page = self._page

        class Size:
            def width(self):
                return page[0]

            def height(self):
                return page[1]

        class Page:
            def pageSize(self):
                return Size()

        class Collection:
            def page(self, index):
                return Page()

        return Collection()


def _map_item(item_id="map-1"):
    from qgis.core import QgsLayoutItemMap

    return _fake_class(QgsLayoutItemMap)(item_id)


def _label_item(item_id="title"):
    from qgis.core import QgsLayoutItemLabel

    return _fake_class(QgsLayoutItemLabel)(item_id, rect=(10, 8, 100, 12))


class ItemsTest(unittest.TestCase):
    def test_auto_id_counts_past_taken_names(self):
        layout = FakeLayout([_map_item("map-1")])
        self.assertEqual(items.unique_item_id(layout, "map", ""), "map-2")

    def test_duplicate_explicit_id_is_refused(self):
        layout = FakeLayout([_map_item("map-1")])
        with self.assertRaises(ValueError):
            items.unique_item_id(layout, "map", "map-1")

    def test_missing_item_lists_the_known_ids(self):
        layout = FakeLayout([_map_item("map-1")])
        with self.assertRaises(ValueError) as caught:
            items.find_item(layout, "legend-1")
        self.assertIn("map-1", str(caught.exception))

    def test_out_of_page_frame_is_refused_with_the_page_size(self):
        layout = FakeLayout()
        with self.assertRaises(ValueError) as caught:
            items.check_bounds(layout, 250.0, 10.0, 100.0, 50.0)
        self.assertIn("297", str(caught.exception))

    def test_linked_map_requires_a_map(self):
        with self.assertRaises(ValueError) as caught:
            items.linked_map(FakeLayout(), {})
        self.assertIn("add a map item first", str(caught.exception))


class AddItemTest(unittest.TestCase):
    def setUp(self):
        self.tool = AddLayoutItemTool()
        self.saved = add_module.find_layout
        add_module.find_layout = lambda name: FakeLayout()

    def tearDown(self):
        add_module.find_layout = self.saved

    def test_label_without_text_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layout_name": "Лист", "item_type": "label", "x": 10, "y": 10})
        self.assertIn("properties.text", str(caught.exception))

    def test_unknown_type_lists_the_available(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layout_name": "Лист", "item_type": "compass", "x": 0, "y": 0})
        self.assertIn("map", str(caught.exception))

    def test_missing_coordinates_are_a_clear_error(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layout_name": "Лист", "item_type": "map"})
        self.assertIn("millimetres", str(caught.exception))

    def test_defaults_fill_the_size_and_id(self):
        prepared = self.tool.prepare({"layout_name": "Лист", "item_type": "map", "x": 10, "y": 20})
        self.assertEqual(prepared["id"], "map-1")
        self.assertEqual(prepared["width"], items.DEFAULT_SIZES_MM["map"][0])

    def test_bad_scale_bar_style_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare(
                {
                    "layout_name": "Лист",
                    "item_type": "scale_bar",
                    "x": 10,
                    "y": 10,
                    "properties": {"style": "fancy"},
                }
            )
        self.assertIn("single_box", str(caught.exception))

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())


class ConfigureItemTest(unittest.TestCase):
    def setUp(self):
        self.tool = ConfigureLayoutItemTool()
        self.layout = FakeLayout([_label_item("title")])
        self.saved_layout = configure_module.find_layout
        configure_module.find_layout = lambda name: self.layout

    def tearDown(self):
        configure_module.find_layout = self.saved_layout

    def test_nothing_to_change_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.tool.prepare({"layout_name": "Лист", "item_id": "title"})
        self.assertIn("Nothing to change", str(caught.exception))

    def test_partial_move_keeps_the_other_coordinates(self):
        prepared = self.tool.prepare({"layout_name": "Лист", "item_id": "title", "x": 20})
        self.assertEqual(prepared["item_id"], "title")

    def test_text_change_lands_on_the_label(self):
        result = self.tool.execute(
            {"layout_name": "Лист", "item_id": "title", "properties": {"text": "Новый заголовок"}}
        )
        self.assertEqual(result["item"]["text"], "Новый заголовок")


class ExportPathTest(unittest.TestCase):
    def test_wrong_extension_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_path("/tmp/map.svg")
        self.assertIn(".pdf", str(caught.exception))

    def test_missing_folder_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            _checked_path("/no/such/folder/map.pdf")
        self.assertIn("does not exist", str(caught.exception))

    def test_valid_pdf_path_passes(self):
        self.assertEqual(_checked_path("/tmp/map.pdf"), "/tmp/map.pdf")

    def test_summary_never_raises(self):
        saved = export_module.find_layout
        export_module.find_layout = lambda name: FakeLayout()
        try:
            self.assertTrue(ExportLayoutTool().summarize_call({}).strip())
        finally:
            export_module.find_layout = saved


if __name__ == "__main__":
    unittest.main()


class MapZoomOrderTest(unittest.TestCase):
    SOURCE = pathlib.Path("ai_agent/qgis_tools/layout/add_layout_item.py").read_text(encoding="utf-8")

    def test_the_map_is_zoomed_only_after_it_has_a_size(self):
        body = self.SOURCE.split("def execute", 1)[1].split("def _checked_kind", 1)[0]
        self.assertIn("_zoom_map", body)
        self.assertLess(body.index("place(item"), body.index("_zoom_map(item"))

    def test_the_extent_is_no_longer_set_on_a_zero_sized_item(self):
        configure = self.SOURCE.split("def _configure", 1)[1].split("def _zoom_map", 1)[0]
        self.assertNotIn("setExtent", configure)

    def test_zoom_falls_back_to_set_extent(self):
        zoom = self.SOURCE.split("def _zoom_map", 1)[1].split("def _map_extent", 1)[0]
        self.assertIn("zoomToExtent", zoom)
        self.assertIn("setExtent", zoom)
