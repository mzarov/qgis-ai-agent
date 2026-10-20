import unittest
from unittest.mock import Mock, patch

from qgis.PyQt.QtGui import QColor

from ai_agent.qgis_tools.annotations import add_annotation as add_module
from ai_agent.qgis_tools.annotations import store as store_module
from ai_agent.qgis_tools.annotations.add_annotation import AddAnnotationTool
from ai_agent.qgis_tools.annotations.manage_annotations import ListAnnotationsTool, RemoveAnnotationTool


class FakeItem:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


class FakeSymbol:
    def __init__(self, colour):
        self._colour = colour

    def clone(self):
        return FakeSymbol(self._colour)

    def color(self):
        return self._colour

    def setColor(self, colour):
        self._colour = colour


class FakeMarker(FakeItem):
    def __init__(self, point):
        super().__init__()
        self._symbol = FakeSymbol(QColor("#ff0000"))

    def symbol(self):
        return self._symbol

    def setSymbol(self, symbol):
        self._symbol = symbol


class FakeLayer:
    def __init__(self):
        self._items = {}
        self._next = 1

    def items(self):
        return dict(self._items)

    def addItem(self, item):
        item_id = f"a{self._next}"
        self._next += 1
        self._items[item_id] = item
        return item_id

    def removeItem(self, item_id):
        self._items.pop(item_id)


class AnnotationsTest(unittest.TestCase):
    def setUp(self):
        self.layer = FakeLayer()
        self.saved = store_module.annotation_layer
        store_module.annotation_layer = lambda: self.layer
        add_module.annotation_layer = lambda: self.layer

    def tearDown(self):
        store_module.annotation_layer = self.saved
        add_module.annotation_layer = self.saved

    def test_a_text_note_lands_on_the_layer(self):
        result = AddAnnotationTool().execute({"kind": "text", "x": 49.1, "y": 55.8, "text": "центр"})
        self.assertEqual(result["id"], "a1")
        self.assertEqual(len(self.layer.items()), 1)

    def test_a_marker_takes_the_asked_colour_and_reads_it_back(self):
        params = {"kind": "marker", "x": 49.1, "y": 55.8, "color": "#2040d0"}
        with patch.object(add_module, "QgsAnnotationMarkerItem", FakeMarker):
            result = AddAnnotationTool().execute(params)
        marker = self.layer.items()[result["id"]]
        self.assertEqual(marker.symbol().color().name(), "#2040d0")
        marker.setSymbol(FakeSymbol(QColor("#ff0000")))
        self.assertFalse(AddAnnotationTool().confirm_applied(params, result), "a red marker is not the blue one asked")

    def test_text_kind_requires_text(self):
        with self.assertRaises(ValueError):
            AddAnnotationTool().prepare({"kind": "text", "x": 1, "y": 2, "text": " "})

    def test_a_marker_needs_no_text(self):
        prepared = AddAnnotationTool().prepare({"kind": "marker", "x": 1, "y": 2})
        self.assertEqual(prepared["kind"], "marker")

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            AddAnnotationTool().prepare({"kind": "arrow", "x": 1, "y": 2})
        self.assertIn("marker", str(caught.exception))

    def test_non_numeric_coordinates_are_refused(self):
        with self.assertRaises(ValueError):
            AddAnnotationTool().prepare({"kind": "marker", "x": "тут", "y": 2})

    def test_listing_reads_ids_and_texts(self):
        self.layer._items["a9"] = FakeItem("заметка")
        listed = ListAnnotationsTool().execute({})
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["annotations"][0]["id"], "a9")
        self.assertEqual(listed["annotations"][0]["text"], "заметка")

    def test_removing_a_known_id_works(self):
        self.layer._items["a5"] = FakeItem()
        RemoveAnnotationTool().execute({"id": "a5"})
        self.assertEqual(self.layer.items(), {})

    def test_removing_an_unknown_id_lists_the_known_ones(self):
        self.layer._items["a5"] = FakeItem()
        with self.assertRaises(ValueError) as caught:
            store_module.remove_item("a7")
        self.assertIn("a5", str(caught.exception))

    def test_removing_an_unknown_id_is_refused_before_apply(self):
        self.layer._items["a5"] = FakeItem()
        with self.assertRaisesRegex(ValueError, "Available: a5"):
            RemoveAnnotationTool().prepare({"id": "a7"})
        self.assertEqual(RemoveAnnotationTool().prepare({"id": " a5 "})["id"], "a5")

    def test_an_unknown_crs_is_refused_before_apply(self):
        invalid = Mock()
        invalid.isValid.return_value = False
        with (
            patch.object(add_module, "QgsCoordinateReferenceSystem", return_value=invalid),
            self.assertRaisesRegex(ValueError, "Unknown CRS 'EPSG:0'"),
        ):
            AddAnnotationTool().prepare({"kind": "marker", "x": 1, "y": 2, "crs": "EPSG:0"})

    def test_a_failed_transform_is_reported_not_swallowed(self):
        source = Mock()
        source.isValid.return_value = True
        source.authid.return_value = "EPSG:4326"
        target = Mock()
        target.isValid.return_value = True
        target.authid.return_value = "EPSG:3857"
        project = Mock()
        project.crs.return_value = target
        point = Mock()
        point.transform.side_effect = RuntimeError("latitude out of range")
        with (
            patch.object(add_module, "QgsCoordinateReferenceSystem", return_value=source),
            patch.object(add_module.QgsProject, "instance", return_value=project),
            patch.object(add_module, "QgsPoint", return_value=point),
            self.assertRaisesRegex(ValueError, "latitude out of range"),
        ):
            AddAnnotationTool().execute({"kind": "marker", "x": 10, "y": 95})
        self.assertEqual(self.layer.items(), {})

    def test_two_crss_without_an_authority_id_are_still_transformed_between(self):
        source, target = Mock(), Mock()
        for crs in (source, target):
            crs.isValid.return_value = True
            crs.authid.return_value = ""
        project = Mock()
        project.crs.return_value = target
        point = Mock()
        with (
            patch.object(add_module.QgsProject, "instance", return_value=project),
            patch.object(add_module, "QgsPoint", return_value=point),
            patch.object(add_module, "QgsCoordinateTransform") as transform,
        ):
            add_module._to_layer_point(500000.0, 6000000.0, source)
        transform.assert_called_once_with(source, target, project)
        point.transform.assert_called_once_with(transform.return_value)

    def test_summaries_never_raise(self):
        for tool in (AddAnnotationTool(), ListAnnotationsTool(), RemoveAnnotationTool()):
            self.assertTrue(tool.summarize_call({}).strip())


if __name__ == "__main__":
    unittest.main()
