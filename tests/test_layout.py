import unittest
from unittest.mock import Mock, patch

from qgis.core import QgsVectorLayer

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

    def addLayoutItem(self, item):
        self._items.append(item)

    def removeLayoutItem(self, item):
        self._items.remove(item)

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


class MapCreationTest(unittest.TestCase):
    def setUp(self):
        self.layout = FakeLayout()
        self.item = Mock()
        self.item.id.return_value = "map-1"
        self.extent = object()
        self.tool = AddLayoutItemTool()
        self.params = {"layout_name": "Sheet", "item_type": "map", "x": 10, "y": 10}
        for target, value in (
            ("find_layout", lambda _: self.layout),
            ("_map_view", lambda _: (self.extent, None)),
        ):
            replacement = patch.object(add_module, target, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.dict(add_module.TYPE_CLASSES, {"map": lambda _: self.item})
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_map_is_sized_before_zoom_and_added_once(self):
        events = []
        self.item.zoomToExtent.side_effect = lambda extent: events.append("zoom")
        with patch.object(add_module, "place", side_effect=lambda *args: events.append("place")):
            self.tool.execute(self.params)
        self.assertEqual(events, ["place", "zoom"])
        self.assertEqual(self.layout.items(), [self.item])

    def test_invalid_extent_fails_before_adding_any_item(self):
        with patch.object(add_module, "_map_view", side_effect=ValueError("no spatial features")):
            for operation in (self.tool.prepare, self.tool.execute):
                with self.subTest(operation=operation.__name__), self.assertRaises(ValueError):
                    operation(self.params)
        self.assertEqual(self.layout.items(), [])
        self.item.setId.assert_not_called()

    def test_placement_failure_removes_the_new_item(self):
        with (
            patch.object(add_module, "place", side_effect=RuntimeError("placement failed")),
            self.assertRaisesRegex(RuntimeError, "placement failed"),
        ):
            self.tool.execute(self.params)
        self.assertEqual(self.layout.items(), [])

    def test_zoom_failure_removes_the_new_item(self):
        self.item.zoomToExtent.side_effect = RuntimeError("zoom failed")
        self.item.setExtent.side_effect = RuntimeError("extent failed")
        with self.assertRaisesRegex(RuntimeError, "extent failed"):
            self.tool.execute(self.params)
        self.assertEqual(self.layout.items(), [])

    def test_zoom_uses_fallback_when_supported_by_the_item(self):
        self.item.zoomToExtent.side_effect = RuntimeError("zoom failed")
        self.tool.execute(self.params)
        self.item.setExtent.assert_called_once_with(self.extent)
        self.assertEqual(self.layout.items(), [self.item])

    def test_page_bounds_are_rechecked_before_execution(self):
        with self.assertRaisesRegex(ValueError, "sticks out"):
            self.tool.execute({**self.params, "x": 1000})
        self.assertEqual(self.layout.items(), [])

    def test_map_uses_the_crs_of_its_resolved_extent(self):
        crs = object()
        with patch.object(add_module, "_map_view", return_value=(self.extent, crs)):
            self.tool.execute(self.params)
        self.item.setCrs.assert_called_once_with(crs)


class Bounds:
    def __init__(self, xmin, ymin, xmax, ymax):
        self.values = xmin, ymin, xmax, ymax

    def xMinimum(self):
        return self.values[0]

    def yMinimum(self):
        return self.values[1]

    def xMaximum(self):
        return self.values[2]

    def yMaximum(self):
        return self.values[3]

    def width(self):
        return self.xMaximum() - self.xMinimum()

    def height(self):
        return self.yMaximum() - self.yMinimum()

    def isEmpty(self):
        return self.width() <= 0 or self.height() <= 0


class ExtentLayer(QgsVectorLayer):
    def __init__(self, extent, crs, features):
        self.bounds = extent
        self.coordinate_system = crs
        self.features = features
        self.spatial = True

    def extent(self):
        return self.bounds

    def crs(self):
        return self.coordinate_system

    def isSpatial(self):
        return self.spatial

    def featureCount(self):
        return len(self.features)

    def getFeatures(self):
        return iter(self.features)


class MapExtentTest(unittest.TestCase):
    def setUp(self):
        self.crs = Mock()
        self.crs.isValid.return_value = True
        self.crs.isGeographic.return_value = False
        feature = Mock()
        feature.hasGeometry.return_value = True
        feature.geometry.return_value.isEmpty.return_value = False
        self.layer = ExtentLayer(Bounds(0, 0, 100, 0), self.crs, [feature])
        self.project = Mock()
        self.project.crs.return_value = self.crs
        holder = Mock()
        holder.instance.return_value = self.project
        for target, value in (
            ("find_layer_by_name", lambda _: self.layer),
            ("QgsProject", holder),
            ("QgsRectangle", Bounds),
        ):
            replacement = patch.object(add_module, target, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_horizontal_features_receive_nonzero_height(self):
        extent, crs = add_module._map_view({"extent": "points"})
        self.assertGreater(extent.height(), 0)
        self.assertEqual((extent.xMinimum(), extent.xMaximum()), (0, 100))
        self.assertLess(extent.yMinimum(), 0)
        self.assertGreater(extent.yMaximum(), 0)
        self.assertIs(crs, self.crs)

    def test_single_point_at_origin_receives_a_valid_extent(self):
        self.layer.bounds = Bounds(0, 0, 0, 0)
        extent, _ = add_module._map_view({"extent": "point"})
        self.assertFalse(extent.isEmpty())
        self.assertEqual(extent.xMinimum(), -extent.xMaximum())
        self.assertEqual(extent.yMinimum(), -extent.yMaximum())

    def test_empty_nonspatial_and_geometryless_layers_still_fail(self):
        for invalid in ("empty", "nonspatial", "geometryless"):
            with self.subTest(invalid=invalid):
                feature = Mock()
                feature.hasGeometry.return_value = False
                self.layer.features = [] if invalid == "empty" else [feature]
                self.layer.spatial = invalid != "nonspatial"
                with self.assertRaisesRegex(ValueError, "no spatial features"):
                    add_module._map_view({"extent": "points"})

    def test_source_extent_is_transformed_to_the_project_crs(self):
        target = Mock()
        target.isValid.return_value = True
        self.project.crs.return_value = target
        transformed = Bounds(1000, 2000, 3000, 4000)
        transform = Mock()
        transform.transformBoundingBox.return_value = transformed
        with patch.object(add_module, "QgsCoordinateTransform", return_value=transform) as factory:
            extent, crs = add_module._map_view({"extent": "points"})
        factory.assert_called_once_with(self.crs, target, self.project)
        self.assertFalse(transform.transformBoundingBox.call_args.args[0].isEmpty())
        self.assertIs(extent, transformed)
        self.assertIs(crs, target)

    def test_source_crs_is_used_if_the_project_has_none(self):
        target = Mock()
        target.isValid.return_value = False
        self.project.crs.return_value = target
        _, crs = add_module._map_view({"extent": "points"})
        self.assertIs(crs, self.crs)


if __name__ == "__main__":
    unittest.main()
