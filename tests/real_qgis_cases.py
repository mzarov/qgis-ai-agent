import pathlib
import tempfile
import unittest
from unittest.mock import patch

from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QCoreApplication, QEvent
from qgis.PyQt.QtWidgets import QMainWindow

from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.llm.transport import ToolCall
from ai_agent.plugin import QgisAiAgentPlugin
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.common.editing import edit_session
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
