import pathlib
import struct
import tempfile
import unittest
from unittest.mock import patch

from osgeo import gdal
from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QEvent
from qgis.PyQt.QtWidgets import QMainWindow

from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.llm.turns import ToolCall
from ai_agent.plugin import QgisAiAgentPlugin
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.draw.draw_features import DrawFeaturesTool
from ai_agent.qgis_tools.processing.run_processing import RunProcessingTool
from ai_agent.qgis_tools.project.snapshots import take_snapshot
from ai_agent.ui.dock_widget import AgentDockWidget


class GisWorkflowsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-agent-workflow-")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.project = QgsProject.instance()
        self.project.clear()
        self.layer = self._layer("points")

    def tearDown(self):
        self.project.clear()

    def _layer(self, name):
        layer = QgsVectorLayer("Point?crs=EPSG:3857&field=name:string&field=count:integer", name, "memory")
        self.assertTrue(layer.isValid())
        features = []
        for index, x in enumerate((0, 100)):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromWkt(f"POINT ({x} 0)"))
            feature.setAttributes([f"point-{index}", index])
            features.append(feature)
        success, _ = layer.dataProvider().addFeatures(features)
        self.assertTrue(success)
        layer.updateExtents()
        self.project.addMapLayer(layer)
        return layer

    def _run(self, tool_name, **arguments):
        batch = WriteBatch(ToolExecutor())
        queued = batch.add(ToolCall("integration", tool_name, arguments))
        results = batch.apply(lambda call: None, lambda call, result: None)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok, results[0].payload)
        return queued, results[0].payload

    def test_symbol_changes_are_visible_in_the_actual_renderer(self):
        self._run("set_symbol", layer_name=self.layer.name(), properties={"color": "#123456", "size": 4})
        symbol = self.layer.renderer().symbol()
        self.assertEqual(symbol.color().name(), "#123456")
        self.assertAlmostEqual(symbol.size(), 4)

    def test_edits_and_schema_changes_target_one_of_two_identically_named_layers(self):
        other = self._layer(self.layer.name())
        target = {"layer_name": self.layer.name(), "layer_id": self.layer.id()}
        self._run("update_attributes", **target, values={"count": 42})
        self.assertEqual([feature["count"] for feature in self.layer.getFeatures()], [42, 42])
        self.assertEqual([feature["count"] for feature in other.getFeatures()], [0, 1])
        self.assertFalse(self.layer.isEditable())
        self._run("add_field", **target, name="status", type="text")
        self.assertIn("status", self.layer.fields().names())
        self.assertNotIn("status", other.fields().names())
        self._run("delete_features", **target, filter="\"name\" = 'point-0'")
        self.assertEqual(self.layer.featureCount(), 1)
        self.assertEqual(other.featureCount(), 2)

    def test_refused_mutation_is_not_reported_as_success_and_closes_edit_buffer(self):
        tool = ToolExecutor()
        call = ToolCall("failure", "update_attributes", {"layer_name": self.layer.name(), "values": {"count": 42}})
        with patch.object(self.layer, "changeAttributeValue", return_value=False):
            result = tool.run(call)
        self.assertFalse(result.ok)
        self.assertFalse(self.layer.isEditable())
        self.assertEqual([feature["count"] for feature in self.layer.getFeatures()], [0, 1])

    def test_exception_rolls_back_real_uncommitted_changes(self):
        feature = next(self.layer.getFeatures())
        with self.assertRaisesRegex(ValueError, "interrupted"), edit_session(self.layer, "the test edits"):
            self.assertTrue(self.layer.changeAttributeValue(feature.id(), 1, 99))
            raise ValueError("interrupted")
        self.assertFalse(self.layer.isEditable())
        self.assertEqual(self.layer.getFeature(feature.id())["count"], 0)

    def test_processing_builds_buffer_geometries_without_changing_input(self):
        self._run(
            "run_processing",
            algorithm_id="native:buffer",
            parameters={"INPUT": self.layer.id(), "DISTANCE": 10, "SEGMENTS": 8, "DISSOLVE": False},
            output_name="buffers",
        )
        output = self.project.mapLayersByName("buffers")[0]
        self.assertEqual(output.featureCount(), 2)
        for feature in output.getFeatures():
            self.assertAlmostEqual(feature.geometry().area(), 312.1445, places=3)
            self.assertTrue(feature.geometry().isGeosValid())
        self.assertEqual(self.layer.featureCount(), 2)
        self.assertEqual(next(self.layer.getFeatures()).geometry().asWkt(), "Point (0 0)")

    def test_truncate_is_classified_destructive_using_the_real_algorithm(self):
        tool = RunProcessingTool()
        prepared = tool.prepare({"algorithm_id": "native:truncatetable", "parameters": {"INPUT": self.layer.id()}})
        self.assertEqual(tool.safety_for(prepared), SAFETY_DESTRUCTIVE)
        self.assertTrue(tool.has_external_effect(prepared))
        self.assertEqual(self.layer.featureCount(), 2)

    def test_snapshot_restores_styling_and_keeps_file_backed_features(self):
        path = self.root / "points.gpkg"
        self._run("export_layer", layer_name=self.layer.name(), path=str(path))
        self.project.removeMapLayer(self.layer.id())
        self.layer = QgsVectorLayer(str(path), "persisted", "ogr")
        self.assertTrue(self.layer.isValid())
        self.project.addMapLayer(self.layer)
        identifier = self.layer.id()
        self.assertTrue(take_snapshot())
        self._run("set_opacity", layer_name="persisted", opacity=0.25)
        self.assertAlmostEqual(self.layer.opacity(), 0.25)
        self._run("undo_last_apply")
        restored = self.project.mapLayer(identifier)
        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored.opacity(), 1.0)
        self.assertEqual(restored.featureCount(), 2)

    def test_undo_brings_scratch_layers_back_with_their_features(self):
        identifier = self.layer.id()
        self.assertTrue(take_snapshot())
        self._run("remove_layer", layer_name=self.layer.name())
        self.assertIsNone(self.project.mapLayer(identifier))
        _, result = self._run("undo_last_apply")
        restored = self.project.mapLayer(identifier)
        self.assertIsNotNone(restored)
        self.assertNotIn("empty_scratch_layers", result)
        self.assertEqual(sorted(feature["name"] for feature in restored.getFeatures()), ["point-0", "point-1"])
        self.assertEqual(
            sorted(feature.geometry().asWkt() for feature in restored.getFeatures()),
            [
                "Point (0 0)",
                "Point (100 0)",
            ],
        )

    def test_a_drawn_utm_point_and_its_buffer_chain_in_one_batch(self):
        batch = WriteBatch(ToolExecutor())
        point = {
            "new_layer_name": "Town hall",
            "geometry": "point",
            "layer_crs": "utm",
            "features": [{"coordinates": [[49.11, 55.79]], "attributes": {"name": "Town hall"}}],
        }
        batch.add(ToolCall("draw", "draw_features", point))
        buffer = {
            "algorithm_id": "native:buffer",
            "parameters": {"INPUT": "Town hall", "DISTANCE": 500},
            "output_name": "Town hall 500 m",
        }
        batch.add(ToolCall("buffer", "run_processing", buffer))
        results = batch.apply(lambda call: None, lambda call, result: None)
        self.assertTrue(all(result.ok for result in results), [result.payload for result in results])
        drawn = self.project.mapLayersByName("Town hall")[0]
        self.assertEqual((drawn.providerType(), drawn.crs().authid()), ("memory", "EPSG:32639"))
        self.assertEqual(next(drawn.getFeatures())["name"], "Town hall")
        zone = next(self.project.mapLayersByName("Town hall 500 m")[0].getFeatures())
        self.assertAlmostEqual(zone.geometry().boundingBox().width(), 1000, delta=1)

    def test_drawing_into_a_file_layer_commits_in_its_crs_and_asks_twice(self):
        path = self.root / "points.gpkg"
        self._run("export_layer", layer_name=self.layer.name(), path=str(path))
        persisted = QgsVectorLayer(str(path), "persisted", "ogr")
        self.assertTrue(persisted.isValid())
        self.project.addMapLayer(persisted)
        arguments = {
            "layer_name": "persisted",
            "geometry": "point",
            "features": [{"coordinates": [[37.62, 55.75]], "attributes": {"name": "Kremlin", "count": 7}}],
        }
        tool = DrawFeaturesTool()
        self.assertEqual(tool.safety_for(tool.prepare(arguments)), SAFETY_DESTRUCTIVE)
        self._run("draw_features", **arguments)
        self.assertFalse(persisted.isEditable())
        reread = QgsVectorLayer(str(path), "reread", "ogr")
        self.assertEqual(reread.featureCount(), 3)
        added = [feature for feature in reread.getFeatures() if feature["name"] == "Kremlin"][0]
        self.assertEqual(added["count"], 7)
        self.assertAlmostEqual(added.geometry().asPoint().x(), 4187839.69, delta=1)

    def test_an_open_ring_closes_and_a_crossing_ring_never_queues(self):
        ring = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]
        self._run("draw_features", new_layer_name="Zone", geometry="polygon", features=[{"coordinates": ring}])
        polygon = next(self.project.mapLayersByName("Zone")[0].getFeatures()).geometry()
        self.assertTrue(polygon.isGeosValid())
        vertices = polygon.asPolygon()[0]
        self.assertEqual(len(vertices), 4)
        self.assertEqual(vertices[0], vertices[-1])
        self.assertAlmostEqual(polygon.area(), 50.0)
        bow_tie = [[0.0, 0.0], [10.0, 10.0], [10.0, 0.0], [0.0, 10.0]]
        batch = WriteBatch(ToolExecutor())
        crossing = {"new_layer_name": "Bow tie", "geometry": "polygon", "features": [{"coordinates": bow_tie}]}
        with self.assertRaisesRegex(ValueError, "crosses itself"):
            batch.add(ToolCall("crossing", "draw_features", crossing))
        self.assertEqual(batch.pending(), [])

    def test_undo_removes_a_drawn_scratch_layer(self):
        self.assertTrue(take_snapshot())
        line = {"new_layer_name": "Route", "geometry": "line", "features": [{"coordinates": [[0, 0], [1, 1]]}]}
        self._run("draw_features", **line)
        self.assertEqual(len(self.project.mapLayersByName("Route")), 1)
        self._run("undo_last_apply")
        self.assertEqual(self.project.mapLayersByName("Route"), [])

    def test_a_text_virtual_field_shows_values_not_null(self):
        queued, result = self._run("add_field", layer_name=self.layer.name(), name="label", expression="upper(name)")
        self.assertEqual(queued.arguments["type"], "text")
        self.assertEqual(result["type"], "text")
        self.assertEqual(sorted(feature["label"] for feature in self.layer.getFeatures()), ["POINT-0", "POINT-1"])

    def test_native_aggregates_answer_filtered_questions(self):
        tool = ToolExecutor()
        count = tool.run(
            ToolCall(
                "count", "query_layer", {"layer_name": self.layer.name(), "aggregate": "count", "filter": "count > 0"}
            )
        )
        total = tool.run(
            ToolCall(
                "sum", "query_layer", {"layer_name": self.layer.name(), "aggregate": "sum", "expression": "count + 1"}
            )
        )
        self.assertEqual((count.payload["matched"], count.payload["value"]), (1, 1))
        self.assertEqual((total.payload["matched"], total.payload["value"]), (2, 3.0))

    def test_changing_live_labels_keeps_the_field_and_the_rest(self):
        self._run("set_labels", layer_name=self.layer.name(), properties={"field": "name", "size": 14})
        self._run("set_labels", layer_name=self.layer.name(), properties={"bold": True})
        settings = self.layer.labeling().settings()
        self.assertEqual(settings.fieldName, "name")
        self.assertAlmostEqual(settings.format().size(), 14)
        self.assertTrue(settings.format().font().bold())

    def test_a_csv_export_keeps_the_geometry(self):
        path = self.root / "points.csv"
        self._run("export_layer", layer_name=self.layer.name(), path=str(path))
        header = path.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("WKT", header)

    def test_bookmarks_are_saved_into_the_project(self):
        before = len(self.project.bookmarkManager().bookmarks())
        self._run("save_bookmark", name="centre")
        names = [bookmark.name() for bookmark in self.project.bookmarkManager().bookmarks()]
        self.assertEqual(len(names), before + 1)
        self.assertIn("centre", names)

    def test_a_raster_style_with_no_data_uses_the_hidden_range(self):
        path = self.root / "dem.tif"
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(str(path), 20, 20, 1, gdal.GDT_Float32)
        dataset.SetGeoTransform((0, 1, 0, 20, 0, -1))
        values = [-9999.0] + [float(value) for value in range(1, 400)]
        dataset.GetRasterBand(1).WriteRaster(0, 0, 20, 20, struct.pack("400f", *values))
        dataset = None
        raster = QgsRasterLayer(str(path), "dem")
        self.assertTrue(raster.isValid())
        self.project.addMapLayer(raster)
        _, result = self._run("set_raster_style", layer_name="dem", mode="gray", no_data_values=[-9999])
        self.assertEqual((result["min"], result["max"]), (1.0, 399.0))

    def test_layout_export_produces_a_pdf_with_real_layout_items(self):
        self._run("create_layout", name="Sheet", page="a4", orientation="landscape")
        self._run(
            "add_layout_item",
            layout_name="Sheet",
            item_type="map",
            x=10,
            y=10,
            width=100,
            height=100,
            properties={"extent": self.layer.name()},
        )
        path = self.root / "sheet.pdf"
        self._run("export_layout", layout_name="Sheet", path=str(path))
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
        self.assertGreater(path.stat().st_size, 1000)


class _Interface:
    def __init__(self):
        self.window = QMainWindow()
        self.actions = []

    def mainWindow(self):
        return self.window

    def addPluginToMenu(self, title, action):
        self.actions.append(action)

    def removePluginMenu(self, title, action):
        self.actions.remove(action)

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


class PluginLifecycleTest(unittest.TestCase):
    def test_feed_popups_and_settings_work_under_real_qt(self):
        from ai_agent.ui.settings_dialog import SettingsDialog

        iface = _Interface()
        plugin = QgisAiAgentPlugin(iface)
        try:
            plugin.initGui()
            plugin.run()
            dock = plugin.dock_widget
            dock.add_user_message("Colour the <b>rivers</b>")
            dock.add_thinking_chunk("Checking the layer first.")
            dock.add_tool_message("Reading the project.")
            dock.add_stream_chunk("Half an ")
            dock.add_stream_chunk("answer")
            QCoreApplication.processEvents()
            self.assertEqual(dock.keep_stream(), "Half an answer")
            dock.conversation.add_assistant_message("**Done**: two steps.")
            dock.add_plan_message(["Colour rivers · reversible"])
            dock.add_system_message("Run stopped.")
            QCoreApplication.processEvents()

            composer = dock.composer
            composer.set_skill_source(lambda: [("osm", "OpenStreetMap", "builtin"), ("style", "Style", "builtin")])
            composer.set_layer_source(lambda: [("Main roads", "line", "layer"), ("rivers", "line", "layer")])
            composer._edit.clear()
            composer._edit.insertPlainText("/o")
            QCoreApplication.processEvents()
            self.assertFalse(composer._popup.isHidden())
            self.assertEqual(composer._popup.current_name(), "osm")
            composer._on_complete()
            self.assertEqual(composer._edit.toPlainText(), "/osm ")

            composer._edit.clear()
            composer._edit.insertPlainText("paint @ma")
            QCoreApplication.processEvents()
            self.assertFalse(composer._popup.isHidden())
            composer._on_complete()
            self.assertEqual(composer._edit.toPlainText(), 'paint @"Main roads" ')
            self.assertTrue(composer._popup.isHidden())

            dialog = SettingsDialog(dock)
            QCoreApplication.processEvents()
            dialog.reject()
            dialog.deleteLater()
            QCoreApplication.processEvents()
        finally:
            plugin.unload()
            iface.window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_plugin_builds_real_widgets_and_unloads(self):
        iface = _Interface()
        plugin = QgisAiAgentPlugin(iface)
        try:
            plugin.initGui()
            self.assertEqual(len(iface.actions), 1)
            plugin.run()
            self.assertIsNotNone(plugin.dock_widget)
            self.assertIsNotNone(plugin._orchestrator)
            QgsProject.instance().clear()
            QCoreApplication.processEvents()
            plugin.unload()
            self.assertEqual(iface.actions, [])
            self.assertIsNone(plugin._orchestrator)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.assertEqual(iface.window.findChildren(AgentDockWidget), [])
            plugin.unload()
        finally:
            if plugin._orchestrator is not None:
                plugin.unload()
            iface.window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
