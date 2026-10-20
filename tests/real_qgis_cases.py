import json
import pathlib
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from osgeo import gdal, osr
from processing.core.ProcessingConfig import ProcessingConfig
from processing.modeler.ModelerUtils import ModelerUtils
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsMapRendererSequentialJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProcessingContext,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsGui
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QEventLoop, QSize, QTimer
from qgis.PyQt.QtWidgets import QMainWindow

from ai_agent.core.agent.batch import WriteBatch
from ai_agent.core.agent.executor import ToolExecutor
from ai_agent.core.context.project import measurement_line
from ai_agent.core.llm.turns import ToolCall
from ai_agent.i18n import tr_n
from ai_agent.plugin import QgisAiAgentPlugin
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE
from ai_agent.qgis_tools.charts import chart_layer
from ai_agent.qgis_tools.common.background import STOPPED, InTask
from ai_agent.qgis_tools.common.editing import edit_session
from ai_agent.qgis_tools.common.layers import suggest_metric_crs
from ai_agent.qgis_tools.draw.draw_features import DrawFeaturesTool
from ai_agent.qgis_tools.processing import model_builder
from ai_agent.qgis_tools.processing.run_processing import RunProcessingTool
from ai_agent.qgis_tools.project.snapshots import take_snapshot
from ai_agent.qgis_tools.quality import scan as quality_scan
from ai_agent.qgis_tools.registry import get_tool_by_name
from ai_agent.ui.dock_widget import AgentDockWidget

BACKGROUND_WAIT_S = 120
WORK_ENDED_S = 1.0
MANY_POINTS = 20000
MODEL_NAME = "Buffer in UTM"
MOSCOW_POINTS = ("POINT (37.6 55.75)", "POINT (37.7 55.8)")
CUSTOM_WEST = "PROJ:+proj=tmerc +lat_0=0 +lon_0=30 +k=1 +x_0=500000 +y_0=0 +ellps=WGS84 +units=m +no_defs"
CUSTOM_EAST = "PROJ:+proj=tmerc +lat_0=0 +lon_0=33 +k=1 +x_0=500000 +y_0=0 +ellps=WGS84 +units=m +no_defs"
CUSTOM_POINT = (500000.0, 6000000.0)


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

    def _applied(self, batch, progress=None):
        ended = []
        batch.apply(lambda call: None, lambda call, result: None, done=ended.append, on_progress=progress)
        deadline = time.monotonic() + BACKGROUND_WAIT_S
        while not ended and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            time.sleep(0.005)
        self.assertTrue(ended, "the batch never ended")
        return ended[0]

    def _run(self, tool_name, **arguments):
        batch = WriteBatch(ToolExecutor())
        queued = batch.add(ToolCall("integration", tool_name, arguments))
        results = self._applied(batch)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok, results[0].payload)
        return queued, results[0].payload

    def test_an_export_onto_a_layers_own_file_is_refused(self):
        source = self.root / "roads.gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        QgsVectorFileWriter.writeAsVectorFormatV3(self.layer, str(source), QgsCoordinateTransformContext(), options)
        roads = QgsVectorLayer(str(source), "roads", "ogr")
        self.project.addMapLayer(roads)
        batch = WriteBatch(ToolExecutor())
        for overwrite in (False, True):
            with self.subTest(overwrite=overwrite):
                arguments = {"layer_name": "roads", "path": str(source), "overwrite": overwrite}
                with self.assertRaisesRegex(ValueError, "holds the data of layer 'roads'"):
                    batch.add(ToolCall("export", "export_layer", arguments))
        self.assertEqual(roads.featureCount(), 2)

    def test_a_project_in_web_mercator_never_offers_it_for_metres(self):
        schools = QgsVectorLayer("Point?crs=EPSG:4326", "schools", "memory")
        feature = QgsFeature(schools.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT (37.62 55.75)"))
        schools.dataProvider().addFeatures([feature])
        schools.updateExtents()
        self.project.removeAllMapLayers()
        self.project.addMapLayer(schools)
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.project.setEllipsoid("NONE")
        self.assertEqual(suggest_metric_crs(schools), "EPSG:32637")
        self.assertIn("transform the geometry to EPSG:32637 first", measurement_line(self.project))
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:32637"))
        self.assertEqual(suggest_metric_crs(schools), "EPSG:32637", "a local projected project CRS is kept")
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:2154"))
        self.assertEqual(suggest_metric_crs(schools), "EPSG:2154")

    def test_a_text_note_and_a_marker_land_on_the_map(self):
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        _, note = self._run("add_annotation", kind="text", x=37.6175, y=55.752, text="start here")
        _, marker = self._run("add_annotation", kind="marker", x=37.62, y=55.75)
        items = self.project.mainAnnotationLayer().items()
        self.assertIn(note["id"], items)
        self.assertIn(marker["id"], items)
        text = items[note["id"]]
        self.assertEqual(text.text(), "start here")
        self.assertAlmostEqual(text.point().y(), 7_509_000, delta=5_000, msg="the note is not where Moscow is")

    def test_a_note_reads_back_with_its_place_in_lon_lat(self):
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        queued, note = self._run("add_annotation", kind="text", x=37.6175, y=55.752, text="start here")
        tool = get_tool_by_name("add_annotation")
        self.assertTrue(tool.confirm_applied(queued.arguments, note))
        self.assertFalse(tool.confirm_applied({**queued.arguments, "text": "end here"}, note))
        self.assertFalse(tool.confirm_applied({**queued.arguments, "x": 30.3}, note), "a note in the wrong place")
        listed = get_tool_by_name("list_annotations").execute({})["annotations"]
        place = next((item["lon"], item["lat"]) for item in listed if item["id"] == note["id"])
        self.assertAlmostEqual(place[0], 37.6175, places=5)
        self.assertAlmostEqual(place[1], 55.752, places=5)

    def test_a_marker_and_a_note_come_in_the_asked_colour(self):
        tool = get_tool_by_name("add_annotation")
        for kind, extra in (("marker", {}), ("text", {"text": "start here"})):
            with self.subTest(kind=kind):
                queued, added = self._run("add_annotation", kind=kind, x=37.62, y=55.75, color="#2040d0", **extra)
                item = self.project.mainAnnotationLayer().items()[added["id"]]
                colour = item.symbol().color() if kind == "marker" else item.format().color()
                self.assertEqual(colour.name(), "#2040d0")
                self.assertTrue(tool.confirm_applied(queued.arguments, added))
                self.assertFalse(tool.confirm_applied({**queued.arguments, "color": "#d02020"}, added))

    def _custom_crs_target(self):
        west, east = QgsCoordinateReferenceSystem(CUSTOM_WEST), QgsCoordinateReferenceSystem(CUSTOM_EAST)
        self.assertTrue(west.isValid() and east.isValid())
        self.assertEqual((west.authid(), east.authid()), ("", ""))
        target = QgsCoordinateTransform(west, east, self.project).transform(QgsPointXY(*CUSTOM_POINT))
        self.assertGreater(abs(target.x() - CUSTOM_POINT[0]), 100_000, "the zones must be far apart")
        return east, target

    def test_a_note_between_two_custom_crss_lands_where_asked(self):
        east, target = self._custom_crs_target()
        self.project.setCrs(east)
        x, y = CUSTOM_POINT
        queued, marker = self._run("add_annotation", kind="marker", x=x, y=y, crs=CUSTOM_WEST)
        centre = self.project.mainAnnotationLayer().items()[marker["id"]].boundingBox().center()
        self.assertAlmostEqual(centre.x(), target.x(), delta=0.01)
        self.assertAlmostEqual(centre.y(), target.y(), delta=0.01)
        self.assertTrue(get_tool_by_name("add_annotation").confirm_applied(queued.arguments, marker))

    def test_drawing_between_two_custom_crss_moves_the_coordinates(self):
        east, target = self._custom_crs_target()
        survey = QgsVectorLayer("Point", "survey", "memory")
        survey.setCrs(east)
        self.project.addMapLayer(survey)
        features = [{"coordinates": [list(CUSTOM_POINT)]}]
        self._run("draw_features", layer_name="survey", geometry="point", crs=CUSTOM_WEST, features=features)
        drawn = next(survey.getFeatures()).geometry().asPoint()
        self.assertAlmostEqual(drawn.x(), target.x(), delta=0.01)
        self.assertAlmostEqual(drawn.y(), target.y(), delta=0.01)

    def test_a_graduated_style_brings_its_legend_for_the_feed_only(self):
        batch = WriteBatch(ToolExecutor())
        arguments = {"layer_name": self.layer.name(), "field": "count", "classes": 2}
        batch.add(ToolCall("graduate", "set_graduated", arguments))
        result = self._applied(batch)[0]
        self.assertTrue(result.ok, result.payload)
        self.assertNotIn("visual_for_user", result.payload, "the legend reached the model's payload")
        legend = result.visual
        self.assertEqual((legend["type"], legend["kind"], legend["title"]), ("legend", "ranges", self.layer.name()))
        self.assertEqual(len(legend["items"]), 2)
        ranges = self.layer.renderer().ranges()
        self.assertEqual(legend["items"][0]["color"], ranges[0].symbol().color().name())
        self.assertEqual(legend["items"][-1]["high"], ranges[-1].upperValue())

    def test_a_class_count_other_than_asked_is_said_with_the_result(self):
        _, jenks = self._run("set_graduated", layer_name=self.layer.name(), field="count", classes=5, mode="jenks")
        self.assertLess(jenks["class_count"], 5)
        self.assertIn("mode=equal", jenks["note"])
        _, equal = self._run("set_graduated", layer_name=self.layer.name(), field="count", classes=5, mode="equal")
        self.assertEqual(equal["class_count"], 5)
        self.assertNotIn("note", equal)

    def test_a_one_point_layer_is_framed_with_the_area_around_it(self):
        from types import SimpleNamespace

        from qgis.gui import QgsMapCanvas

        point = QgsVectorLayer("Point?crs=EPSG:4326", "Red Square", "memory")
        feature = QgsFeature(point.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT (37.6208 55.7539)"))
        point.dataProvider().addFeatures([feature])
        point.updateExtents()
        self.project.addMapLayer(point)
        canvas = QgsMapCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        canvas.resize(400, 300)
        canvas.setLayers([point])
        with patch("qgis.utils.iface", SimpleNamespace(mapCanvas=lambda: canvas)):
            result = get_tool_by_name("render_map").execute({"layer_name": "Red Square", "width": 400})
        extent = result["extent"]
        self.assertAlmostEqual(extent["xmax"] - extent["xmin"], 1000, delta=1, msg="500 m either side of the point")
        self.assertTrue(result["image_base64"])

    def test_a_computed_value_is_written_into_a_real_field_on_the_ellipsoid(self):
        cell = QgsVectorLayer("Polygon?crs=EPSG:4326&field=area_ha:double", "cells", "memory")
        feature = QgsFeature(cell.fields())
        ring = "37.45 55.65, 37.53 55.65, 37.53 55.7, 37.45 55.7, 37.45 55.65"
        feature.setGeometry(QgsGeometry.fromWkt(f"POLYGON (({ring}))"))
        cell.dataProvider().addFeatures([feature])
        self.project.addMapLayer(cell)
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.project.setEllipsoid("EPSG:7030")
        _, result = self._run("update_attributes", layer_name="cells", expressions={"area_ha": "$area / 10000"})
        self.assertEqual(result["fields"], ["area_ha"])
        self.assertAlmostEqual(next(cell.getFeatures())["area_ha"], 2801.9, delta=1.0)

    def test_a_count_from_another_layer_is_a_virtual_field(self):
        district = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "districts", "memory")
        feature = QgsFeature(district.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POLYGON ((37 55, 38 55, 38 56, 37 56, 37 55))"))
        district.dataProvider().addFeatures([feature])
        schools = QgsVectorLayer("Point?crs=EPSG:4326", "schools", "memory")
        points = []
        for x in (37.5, 37.6, 39.0):
            point = QgsFeature(schools.fields())
            point.setGeometry(QgsGeometry.fromWkt(f"POINT ({x} 55.5)"))
            points.append(point)
        schools.dataProvider().addFeatures(points)
        self.project.addMapLayers([district, schools])
        expression = "aggregate('schools', 'count', $id, intersects($geometry, geometry(@parent)))"
        self._run("add_field", layer_name="districts", name="schools_n", expression=expression)
        self.assertEqual(next(district.getFeatures())["schools_n"], 2)

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

    def test_a_file_output_takes_the_name_a_later_step_refers_to(self):
        centres = {"INPUT": self.layer.id(), "OUTPUT": str(self.root / "centres.gpkg")}
        zones = {"INPUT": "centres", "DISTANCE": 10, "OUTPUT": str(self.root / "zones.shp")}
        batch = WriteBatch(ToolExecutor())
        for algorithm_id, parameters, name in (
            ("native:centroids", centres, "centres"),
            ("native:buffer", zones, "zones"),
        ):
            batch.add(
                ToolCall(
                    name,
                    "run_processing",
                    {"algorithm_id": algorithm_id, "parameters": parameters, "output_name": name},
                )
            )
        results = self._applied(batch)
        self.assertTrue(all(result.ok for result in results), [result.payload for result in results])
        self.assertEqual([result.payload["result_layer_name"] for result in results], ["centres", "zones"])
        self.assertEqual(self.project.mapLayersByName("centres")[0].source(), centres["OUTPUT"])
        self.assertEqual(self.project.mapLayersByName("zones")[0].featureCount(), 2)

        tool = RunProcessingTool()
        on_main = {
            "algorithm_id": "native:buffer",
            "parameters": {"INPUT": self.layer.id(), "DISTANCE": 10, "OUTPUT": str(self.root / "on_main.gpkg")},
            "output_name": "on the main thread",
        }
        payload = tool.execute(tool.prepare(on_main))
        self.assertEqual(payload["result_layer_name"], "on the main thread")
        self.assertEqual(self.project.mapLayersByName("on the main thread")[0].featureCount(), 2)

    def test_a_long_algorithm_runs_off_the_main_thread_and_reports_progress(self):
        many = QgsVectorLayer("Point?crs=EPSG:3857", "many", "memory")
        features = []
        for index in range(MANY_POINTS):
            feature = QgsFeature(many.fields())
            feature.setGeometry(QgsGeometry.fromWkt(f"POINT ({index * 10} {index % 100 * 10})"))
            features.append(feature)
        many.dataProvider().addFeatures(features)
        self.project.addMapLayer(many)
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start()
        progress = []
        batch = WriteBatch(ToolExecutor())
        batch.add(
            ToolCall(
                "buffer",
                "run_processing",
                {"algorithm_id": "native:buffer", "parameters": {"INPUT": "many", "DISTANCE": 5, "SEGMENTS": 32}},
            )
        )
        results = self._applied(batch, lambda percent, done: progress.append(percent))
        timer.stop()
        self.assertTrue(results[0].ok, results[0].payload)
        self.assertTrue(progress, "the algorithm's progress never reached the batch")
        self.assertGreater(len(ticks), 2, "the main thread was blocked while the algorithm ran")
        self.assertEqual(self.project.mapLayersByName("Buffered")[0].featureCount(), MANY_POINTS)

    def test_a_background_algorithm_past_the_tool_timeout_is_stopped_with_the_limit_named(self):
        batch = WriteBatch(ToolExecutor())
        arguments = {"algorithm_id": "native:buffer", "parameters": {"INPUT": self.layer.id(), "DISTANCE": 10}}
        batch.add(ToolCall("buffer", "run_processing", arguments))
        with patch("ai_agent.config.limits.tool_seconds", return_value=0):
            results = self._applied(batch)
        self.assertFalse(results[0].ok)
        self.assertIn("0 s tool timeout", results[0].payload["error"])
        self.assertEqual(self.project.mapLayersByName("Buffered"), [])

    def test_stopping_cancels_an_algorithm_working_in_the_background(self):
        batch = WriteBatch(ToolExecutor())
        arguments = {"algorithm_id": "native:buffer", "parameters": {"INPUT": self.layer.id(), "DISTANCE": 10}}
        batch.add(ToolCall("buffer", "run_processing", arguments))
        batch.add(ToolCall("opacity", "set_opacity", {"layer_name": self.layer.name(), "opacity": 0.5}))
        ended = []
        batch.apply(lambda call: None, lambda call, result: None, done=ended.append)
        batch.clear()
        deadline = time.monotonic() + BACKGROUND_WAIT_S
        while not ended and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        self.assertEqual([result.ok for result in ended[0]], [False, False])
        self.assertAlmostEqual(self.layer.opacity(), 1.0, msg="a step after the stopped one ran")

    def test_a_stop_after_a_background_work_ended_keeps_nothing(self):
        worked = threading.Event()
        made, ended = [], []
        work = InTask("answer", lambda feedback: worked.set() or "answer", made.append)
        work.finished.connect(ended.append)
        work.start()
        self.assertTrue(worked.wait(BACKGROUND_WAIT_S), "the work never ran")
        time.sleep(WORK_ENDED_S)
        work.cancel()
        deadline = time.monotonic() + BACKGROUND_WAIT_S
        while not ended and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        self.assertEqual(made, [], "the work's value was used after the stop")
        self.assertEqual([str(outcome) for outcome in ended], [STOPPED])

    def _ended_with(self, work):
        ended = []
        work.finished.connect(ended.append)
        work.start()
        self.assertEqual(ended, [], "finished arrived before start returned")
        deadline = time.monotonic() + BACKGROUND_WAIT_S
        while not ended and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        self.assertEqual(len(ended), 1, "the work never ended")
        return ended[0]

    def test_a_work_runs_off_the_main_thread_and_its_result_is_made_on_it(self):
        threads = {}

        def work(feedback):
            threads["work"] = threading.current_thread() is threading.main_thread()
            return 42

        def complete(value):
            threads["complete"] = threading.current_thread() is threading.main_thread()
            return {"value": value}

        self.assertEqual(self._ended_with(InTask("threads", work, complete)), {"value": 42})
        self.assertEqual(threads, {"work": False, "complete": True})

    def test_a_work_that_raises_ends_with_its_error_and_keeps_nothing(self):
        made = []
        outcome = self._ended_with(InTask("broken", lambda feedback: 1 / 0, made.append))
        self.assertIsInstance(outcome, ZeroDivisionError)
        self.assertEqual(made, [])

    def test_a_result_that_cannot_be_made_is_the_outcome(self):
        def complete(value):
            raise ValueError(f"no features in the {value}")

        outcome = self._ended_with(InTask("empty", lambda feedback: "answer", complete))
        self.assertEqual(str(outcome), "no features in the answer")

    def test_a_work_that_cannot_launch_ends_after_start_returns(self):
        class Unlaunchable(InTask):
            def _launch(self):
                raise RuntimeError("no task manager")

        outcome = self._ended_with(Unlaunchable("never", lambda feedback: None, lambda value: {}))
        self.assertEqual(str(outcome), "no task manager")

    def test_truncate_is_classified_destructive_using_the_real_algorithm(self):
        tool = RunProcessingTool()
        prepared = tool.prepare({"algorithm_id": "native:truncatetable", "parameters": {"INPUT": self.layer.id()}})
        self.assertEqual(tool.safety_for(prepared), SAFETY_DESTRUCTIVE)
        self.assertTrue(tool.has_external_effect(prepared))
        self.assertEqual(self.layer.featureCount(), 2)

    def test_an_algorithm_past_the_tool_timeout_is_cancelled_with_the_limit_named(self):
        tool = RunProcessingTool()
        arguments = {
            "algorithm_id": "native:buffer",
            "parameters": {"INPUT": self.layer.id(), "DISTANCE": 10, "OUTPUT": "memory:"},
            "load_output": False,
        }
        prepared = tool.prepare(arguments)
        with patch("ai_agent.config.limits.tool_seconds", return_value=0), self.assertRaises(TimeoutError) as caught:
            tool.execute(prepared)
        self.assertIn("0 s tool timeout", str(caught.exception))
        _queued, payload = self._run("run_processing", **arguments)
        self.assertEqual(payload["algorithm_id"], "native:buffer", "with the usual limit it runs")

    def _models_folder(self):
        folder = self.root / "models"
        folder.mkdir()
        saved = ProcessingConfig.getSetting(ModelerUtils.MODELS_FOLDER)
        ProcessingConfig.setSettingValue(ModelerUtils.MODELS_FOLDER, str(folder))

        def restore():
            ProcessingConfig.setSettingValue(ModelerUtils.MODELS_FOLDER, saved)
            QgsApplication.processingRegistry().providerById(model_builder.MODEL_PROVIDER_ID).refreshAlgorithms()

        self.addCleanup(restore)
        self.assertEqual(model_builder.models_folder(), str(folder))
        return folder

    def test_two_steps_become_a_model_that_runs_on_other_data(self):
        folder = self._models_folder()
        arguments = {
            "name": MODEL_NAME,
            "group": "AI Agent tests",
            "inputs": [
                {"name": "points", "type": "vector", "description": "Points"},
                {"name": "distance", "type": "distance", "default": 100},
            ],
            "steps": [
                {
                    "id": "reproject",
                    "algorithm_id": "native:reprojectlayer",
                    "parameters": {"INPUT": {"input": "points"}, "TARGET_CRS": "EPSG:32637"},
                },
                {
                    "id": "buffer",
                    "algorithm_id": "native:buffer",
                    "parameters": {
                        "INPUT": {"step": "reproject", "output": "OUTPUT"},
                        "DISTANCE": {"input": "distance"},
                        "SEGMENTS": 8,
                        "OUTPUT": "TEMPORARY_OUTPUT",
                    },
                },
            ],
            "outputs": [{"name": "Buffered", "step": "buffer"}],
        }
        queued, payload = self._run("create_processing_model", **arguments)
        model_id = f"model:{MODEL_NAME}"
        self.assertEqual(payload["algorithm_id"], model_id)
        self.assertEqual(payload["path"], str(folder / f"{MODEL_NAME}.model3"))
        self.assertTrue((folder / f"{MODEL_NAME}.model3").is_file())
        self.assertIsNotNone(QgsApplication.processingRegistry().algorithmById(model_id))
        tool = get_tool_by_name("create_processing_model")
        self.assertTrue(tool.confirm_applied(queued.arguments, payload))

        towns = QgsVectorLayer("Point?crs=EPSG:4326", "towns", "memory")
        for wkt in MOSCOW_POINTS:
            feature = QgsFeature(towns.fields())
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            towns.dataProvider().addFeatures([feature])
        towns.updateExtents()
        self.project.addMapLayer(towns)
        self._run(
            "run_processing",
            algorithm_id=model_id,
            parameters={"points": "towns", "distance": 500},
            output_name="town buffers",
        )
        buffers = self.project.mapLayersByName("town buffers")[0]
        self.assertEqual(buffers.featureCount(), len(MOSCOW_POINTS))
        self.assertEqual(buffers.crs().authid(), "EPSG:32637")
        for feature in buffers.getFeatures():
            self.assertAlmostEqual(feature.geometry().area(), 3.14159 * 500**2, delta=0.02 * 3.14159 * 500**2)

        batch = WriteBatch(ToolExecutor())
        with self.assertRaisesRegex(ValueError, "already exists"):
            batch.add(ToolCall("again", "create_processing_model", arguments))
        replacing = batch.add(ToolCall("replace", "create_processing_model", {**arguments, "overwrite": True}))
        self.assertEqual(tool.safety_for(replacing.arguments), SAFETY_DESTRUCTIVE)
        broken = {**arguments, "steps": [{**arguments["steps"][1], "id": "buffer", "parameters": {}}]}
        with self.assertRaisesRegex(ValueError, "INPUT"):
            batch.add(ToolCall("broken", "create_processing_model", {**broken, "name": "Broken", "inputs": []}))

    def test_a_run_from_the_processing_dialog_is_listed_with_its_layer_named(self):
        algorithm = QgsApplication.processingRegistry().createAlgorithmById("native:buffer")
        context = QgsProcessingContext()
        context.setProject(self.project)
        parameters = {"INPUT": self.layer.id(), "DISTANCE": 25, "OUTPUT": "TEMPORARY_OUTPUT"}
        details = {"algorithm_id": algorithm.id(), "parameters": algorithm.asMap(parameters, context)}
        entry_id, added = QgsGui.historyProviderRegistry().addEntry("processing", details)
        self.assertTrue(added)
        QgsGui.historyProviderRegistry().updateEntry(entry_id, {**details, "results": {"OUTPUT": self.layer.id()}})
        payload = get_tool_by_name("list_processing_history").execute({"limit": 5})
        self.assertTrue(payload["available"], payload)
        latest = payload["entries"][-1]
        self.assertEqual(latest["algorithm_id"], "native:buffer")
        self.assertEqual(latest["parameters"]["DISTANCE"], 25)
        self.assertEqual(latest["project_layers"], {"INPUT": "points"})
        self.assertEqual(latest["result_layers"], {"OUTPUT": "points"})
        self.assertTrue(latest["finished"])

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

    def test_undoing_a_style_change_keeps_a_scratch_layers_feature_ids(self):
        third = QgsFeature(self.layer.fields())
        third.setGeometry(QgsGeometry.fromWkt("POINT (200 0)"))
        third.setAttributes(["point-2", 2])
        self.assertTrue(self.layer.dataProvider().addFeatures([third])[0])
        self.assertTrue(self.layer.dataProvider().deleteFeatures([2]))
        self._run("add_field", layer_name=self.layer.name(), name="row", expression="$id")
        identifier = self.layer.id()
        self.assertTrue(take_snapshot())
        self._run("set_opacity", layer_name=self.layer.name(), opacity=0.5)
        _, result = self._run("undo_last_apply")
        restored = self.project.mapLayer(identifier)
        self.assertNotIn("renumbered_scratch_layers", result)
        rows = sorted((feature.id(), feature["name"], feature["row"]) for feature in restored.getFeatures())
        self.assertEqual(rows, [(1, "point-0", 1), (3, "point-2", 3)])
        self.assertEqual(restored.featureCount(), 2)
        added = QgsFeature(restored.fields())
        added.setAttributes(["point-3", 3])
        ok, (fresh,) = restored.dataProvider().addFeatures([added])
        self.assertEqual(fresh.id(), 4, "a feature added after the undo took an id that was in use")

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
        results = self._applied(batch)
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

    def test_a_64_bit_id_reaches_a_drawn_layer_exactly(self):
        osm_id = 2**53 + 1
        features = [{"coordinates": [[37.62, 55.75]], "attributes": {"osm_id": osm_id}}]
        self._run("draw_features", new_layer_name="Nodes", geometry="point", features=features)
        self.assertEqual(next(self.project.mapLayersByName("Nodes")[0].getFeatures())["osm_id"], osm_id)
        too_big = {**features[0], "attributes": {"osm_id": 2**63}}
        appended = {"layer_name": "Nodes", "geometry": "point", "features": [too_big]}
        with self.assertRaisesRegex(ValueError, "64-bit"):
            WriteBatch(ToolExecutor()).add(ToolCall("too big", "draw_features", appended))

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

    def test_selected_only_answers_over_the_selected_features_the_filter_accepts(self):
        numbers = self._memory(
            "Point?crs=EPSG:3857&field=n:integer", "numbers", [(f"POINT ({n} 0)", [n]) for n in (1, 2, 3)]
        )
        numbers.selectByExpression("n <= 2")
        executor = ToolExecutor()

        def query(**arguments):
            arguments = {"layer_name": "numbers", "selected_only": True, "filter": "n >= 2", **arguments}
            result = executor.run(ToolCall("selected", "query_layer", arguments))
            self.assertTrue(result.ok, result.payload)
            return result.payload

        self.assertEqual([row["n"] for row in query()["features"]], [2])
        self.assertEqual(query(aggregate="count")["value"], 1)
        self.assertEqual(query(aggregate="sum", expression="n")["value"], 2)
        self.assertEqual(query(aggregate="concatenate", expression="n")["value"], "2")
        grouped = query(aggregate="count", group_by="n")["groups"]
        self.assertEqual([(group["group"], group["count"]) for group in grouped], [(2, 1)])
        self.assertEqual(query(aggregate="count", filter="n = 3")["value"], 0)

    def test_a_chart_past_the_feature_cap_says_it_is_partial(self):
        rows = [("POINT (0 0)", ["a"]), ("POINT (1 0)", ["a"]), ("POINT (2 0)", ["b"])]
        self._memory("Point?crs=EPSG:3857&field=kind:string", "kinds", rows)
        arguments = {"layer_name": "kinds", "group_by": "kind"}
        whole = ToolExecutor().run(ToolCall("whole", "chart_layer", arguments))
        self.assertTrue(whole.ok, whole.payload)
        self.assertEqual(whole.payload["features"], 3)
        self.assertNotIn("partial", whole.payload)
        with patch.object(chart_layer, "MAX_FEATURES", 2):
            capped = ToolExecutor().run(ToolCall("capped", "chart_layer", arguments))
        self.assertTrue(capped.ok, capped.payload)
        self.assertEqual((capped.payload["features"], capped.payload.get("partial")), (2, True))
        self.assertIn("first 2", capped.payload["note"])

    def _lakes(self):
        self.project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        self.project.setEllipsoid("EPSG:7030")
        memory = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "lakes", "memory")
        # Square degrees mislead: the arctic lake covers twice the equator's, yet is the smaller one.
        rows = [
            ("POLYGON((10 0, 10.01 0, 10.01 0.01, 10 0.01, 10 0))", ["equator lake"]),
            ("POLYGON((10 70, 10.02 70, 10.02 70.01, 10 70.01, 10 70))", ["arctic lake"]),
            ("POLYGON((11 60, 11.0002 60, 11.0002 60.00009, 11 60.00009, 11 60))", ["pond"]),
        ]
        features = []
        for wkt, attributes in rows:
            feature = QgsFeature(memory.fields())
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            feature.setAttributes(attributes)
            features.append(feature)
        memory.dataProvider().addFeatures(features)
        return self._saved(memory, "lakes.gpkg", "GPKG")

    def _saved(self, memory, file_name, driver):
        path = self.root / file_name
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        written = QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(path), QgsCoordinateTransformContext(), options)
        self.assertEqual(written[0], QgsVectorFileWriter.WriterError.NoError, written)
        layer = QgsVectorLayer(str(path), memory.name(), "ogr")
        self.assertTrue(layer.isValid())
        self.project.addMapLayer(layer)
        return layer

    def test_a_filter_and_an_order_measure_on_the_ellipsoid_like_the_aggregates(self):
        lakes = self._lakes()
        query = get_tool_by_name("query_layer")
        small = {"layer_name": "lakes", "filter": "$area < 10000"}
        self.assertEqual([row["name"] for row in query.execute(small)["features"]], ["pond"])
        self.assertEqual(query.execute({**small, "aggregate": "count"})["value"], 1)
        grouped = query.execute({**small, "aggregate": "count", "group_by": "name"})["groups"]
        self.assertEqual([group["group"] for group in grouped], ["pond"])
        largest = query.execute({"layer_name": "lakes", "order_by": "$area DESC", "limit": 1})["features"]
        self.assertEqual([row["name"] for row in largest], ["equator lake"])
        chart = get_tool_by_name("chart_layer").execute({**small, "group_by": "name"})
        self.assertEqual(chart["features"], 1)
        table = get_tool_by_name("show_table").execute({**small, "fields": ["name"]})
        self.assertEqual(table["first_rows"], [["pond"]])
        queued, deleted = self._run("delete_features", **small)
        self.assertEqual((queued.arguments["matched_estimate"], deleted["deleted"]), (1, 1))
        self.assertEqual(sorted(feature["name"] for feature in lakes.getFeatures()), ["arctic lake", "equator lake"])

    def test_a_filter_on_the_selection_finds_the_selected_features(self):
        lakes = self._lakes()
        lakes.selectByExpression("name = 'pond'")
        selected = {"layer_name": "lakes", "filter": "is_selected()"}
        query = get_tool_by_name("query_layer")
        self.assertEqual([row["name"] for row in query.execute(selected)["features"]], ["pond"])
        self.assertEqual(query.execute({**selected, "aggregate": "count"})["value"], 1)
        both = {**selected, "selected_only": True, "filter": "is_selected() and $area < 10000"}
        self.assertEqual(query.execute(both)["matched"], 1)
        update = get_tool_by_name("update_attributes").prepare({**selected, "values": {"name": "tarn"}})
        self.assertEqual(update["matched_estimate"], 1)
        self.assertEqual(get_tool_by_name("delete_features").prepare(selected)["matched_estimate"], 1)
        table = get_tool_by_name("show_table").execute({**selected, "fields": ["name"]})
        self.assertEqual(table["first_rows"], [["pond"]])

    def _memory(self, uri, name, rows):
        layer = QgsVectorLayer(uri, name, "memory")
        self.assertTrue(layer.isValid())
        features = []
        for wkt, attributes in rows:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            feature.setAttributes(attributes)
            features.append(feature)
        self.assertTrue(layer.dataProvider().addFeatures(features)[0])
        layer.updateExtents()
        self.project.addMapLayer(layer)
        return layer

    def _districts_and_schools(self):
        square = "POLYGON(({0} 0, {1} 0, {1} 100, {0} 100, {0} 0))"
        districts = self._memory(
            "Polygon?crs=EPSG:3857&field=name:string&field=code:integer",
            "districts",
            [
                (square.format(0, 100), ["North", 1]),
                (square.format(200, 300), ["South", 2]),
                (square.format(400, 500), ["East", 3]),
            ],
        )
        schools = self._memory(
            "Point?crs=EPSG:3857&field=name:string&field=district:integer&field=capacity:integer",
            "schools",
            [
                ("POINT (10 10)", ["s1", 1, 300]),
                ("POINT (50 50)", ["s2", 1, 500]),
                ("POINT (250 50)", ["s3", 2, 200]),
                ("POINT (900 900)", ["s4", 2, 100]),
            ],
        )
        return districts, schools

    def _query(self, sql):
        return ToolExecutor().run(ToolCall("sql", "query_sql", {"sql": sql}))

    def test_sql_groups_a_join_of_two_layers(self):
        self._districts_and_schools()
        result = self._query(
            'SELECT d.name, count(s.name) AS schools, sum(s.capacity) AS seats FROM "districts" d '
            'JOIN "schools" s ON s.district = d.code GROUP BY d.name ORDER BY d.name;'
        )
        self.assertTrue(result.ok, result.payload)
        self.assertEqual(result.payload["columns"], ["name", "schools", "seats"])
        self.assertEqual(result.payload["rows"], [["North", 2, 800], ["South", 2, 300]])
        self.assertEqual(result.payload["row_count"], 2)

    def test_sql_counts_points_in_polygons(self):
        self._districts_and_schools()
        result = self._query(
            'SELECT d.name, count(s.geometry) AS inside FROM "districts" d LEFT JOIN "schools" s '
            "ON ST_Contains(d.geometry, s.geometry) AND s._search_frame_ = d.geometry GROUP BY d.name ORDER BY d.name"
        )
        self.assertTrue(result.ok, result.payload)
        self.assertEqual(result.payload["rows"], [["East", 0], ["North", 2], ["South", 1]])
        areas = self._query('SELECT name, ST_Area(geometry) AS area, geometry FROM "districts" ORDER BY name')
        self.assertEqual([row[1] for row in areas.payload["rows"]], [10000.0, 10000.0, 10000.0])
        self.assertEqual((areas.payload["geometry"], areas.payload["crs"]), ("polygon", "EPSG:3857"))
        self.assertEqual(areas.payload["columns"], ["name", "area"], "the geometry itself is never sent")

    def test_sql_binds_a_shared_name_only_by_id(self):
        self._districts_and_schools()
        twin = self._memory("Point?crs=EPSG:3857&field=name:string", "schools", [("POINT (0 0)", ["twin"])])
        refused = self._query('SELECT count(*) FROM "schools"')
        self.assertFalse(refused.ok)
        self.assertIn("ambiguous", refused.payload["error"])
        chosen = self._query(f'SELECT name FROM "{twin.id()}"')
        self.assertEqual(chosen.payload["rows"], [["twin"]])

    def test_a_sql_layer_is_added_live_and_valid(self):
        districts, schools = self._districts_and_schools()
        sql = (
            'SELECT d.name, count(s.geometry) AS inside, d.geometry FROM "districts" d LEFT JOIN "schools" s '
            "ON ST_Contains(d.geometry, s.geometry) GROUP BY d.name"
        )
        queued, payload = self._run("create_sql_layer", sql=sql, name="school counts")
        layer = self.project.mapLayer(payload["layer_id"])
        self.assertTrue(layer.isValid())
        self.assertEqual((layer.name(), layer.providerType(), layer.featureCount()), ("school counts", "virtual", 3))
        self.assertEqual((payload["feature_count"], payload["geometry"]), (3, "polygon"))
        self.assertIn("inside", payload["fields"])
        self.assertTrue(get_tool_by_name("create_sql_layer").confirm_applied(queued.arguments, payload))
        extra = QgsFeature(schools.fields())
        extra.setGeometry(QgsGeometry.fromWkt("POINT (450 50)"))
        extra.setAttributes(["s5", 3, 50])
        schools.dataProvider().addFeatures([extra])
        layer.reload()
        counts = {feature["name"]: feature["inside"] for feature in layer.getFeatures()}
        self.assertEqual(counts, {"North": 2, "South": 1, "East": 1})
        with self.assertRaisesRegex(ValueError, "already in the project"):
            WriteBatch(ToolExecutor()).add(ToolCall("again", "create_sql_layer", {"sql": sql, "name": "school counts"}))

    def test_bad_sql_comes_back_as_a_clear_error(self):
        self._districts_and_schools()
        syntax = self._query('SELEC name FROM "districts"')
        self.assertFalse(syntax.ok)
        self.assertIn("Only a read-only SELECT", syntax.payload["error"])
        column = self._query('SELECT nme FROM "districts"')
        self.assertFalse(column.ok)
        self.assertTrue(column.payload["error"].startswith("The query failed: no such column: nme."), column.payload)
        self.assertNotIn("_tview", column.payload["error"])
        broken = self._query("SELECT name FROM \"districts\" WHERE name = = 'North'")
        self.assertIn('near "=": syntax error', broken.payload["error"])
        missing = self._query('SELECT name FROM "distrcts"')
        self.assertIn("distrcts", missing.payload["error"])
        self.assertIn("named in double quotes:", missing.payload["error"])
        for name in ('"districts"', '"schools"', '"points"'):
            self.assertIn(name, missing.payload["error"])
        with self.assertRaisesRegex(ValueError, "The query failed: no such column: nme"):
            WriteBatch(ToolExecutor()).add(
                ToolCall("bad", "create_sql_layer", {"sql": 'SELECT nme FROM "districts"', "name": "never"})
            )
        self.assertEqual(self.project.mapLayersByName("never"), [])

    def test_changing_live_labels_keeps_the_field_and_the_rest(self):
        self._run("set_labels", layer_name=self.layer.name(), properties={"field": "name", "size": 14})
        self._run("set_labels", layer_name=self.layer.name(), properties={"bold": True})
        settings = self.layer.labeling().settings()
        self.assertEqual(settings.fieldName, "name")
        self.assertAlmostEqual(settings.format().size(), 14)
        self.assertTrue(settings.format().font().bold())

    def test_a_new_label_size_comes_in_points_and_millimetres(self):
        self._run("set_labels", layer_name=self.layer.name(), properties={"field": "name", "buffer_size": 1})
        settings = self.layer.labeling().settings()
        text_format = settings.format()
        text_format.setSizeUnit(Qgis.RenderUnit.MapUnits)
        buffer = text_format.buffer()
        buffer.setSizeUnit(Qgis.RenderUnit.MapUnits)
        text_format.setBuffer(buffer)
        settings.setFormat(text_format)
        self.layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        self._run("set_labels", layer_name=self.layer.name(), properties={"bold": True})
        kept = self.layer.labeling().settings().format()
        self.assertEqual((kept.sizeUnit(), kept.buffer().sizeUnit()), (Qgis.RenderUnit.MapUnits,) * 2)
        self._run("set_labels", layer_name=self.layer.name(), properties={"size": 10, "buffer_size": 1.5})
        changed = self.layer.labeling().settings().format()
        self.assertEqual((changed.size(), changed.sizeUnit()), (10.0, Qgis.RenderUnit.Points))
        self.assertEqual((changed.buffer().size(), changed.buffer().sizeUnit()), (1.5, Qgis.RenderUnit.Millimeters))

    def test_a_csv_export_keeps_the_geometry(self):
        path = self.root / "points.csv"
        self._run("export_layer", layer_name=self.layer.name(), path=str(path))
        header = path.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("WKT", header)

    def test_an_export_reads_back_from_the_file_it_wrote(self):
        path = self.root / "points.gpkg"
        queued, payload = self._run("export_layer", layer_name=self.layer.name(), path=str(path))
        arguments = queued.arguments
        tool = get_tool_by_name("export_layer")
        self.assertTrue(tool.confirm_applied(arguments, payload))
        self.layer.selectByIds([next(self.layer.getFeatures()).id()])
        selected_only = {**payload, "selected_only": True}
        self.assertFalse(tool.confirm_applied(arguments, selected_only), "one selected, two in the file")
        path.write_bytes(b"")
        self.assertFalse(tool.confirm_applied(arguments, payload), "an empty file is no export")

    def test_bookmarks_are_saved_into_the_project(self):
        before = len(self.project.bookmarkManager().bookmarks())
        self._run("save_bookmark", name="centre")
        names = [bookmark.name() for bookmark in self.project.bookmarkManager().bookmarks()]
        self.assertEqual(len(names), before + 1)
        self.assertIn("centre", names)

    def test_a_gray_raster_stretches_the_range_left_after_no_data(self):
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
        stretch = raster.renderer().contrastEnhancement()
        self.assertIsNotNone(stretch, "gray without a stretch paints the raw values, wrapping past 255")
        self.assertEqual((stretch.minimumValue(), stretch.maximumValue()), (1.0, 399.0))
        image = self._rendered(raster, 20)
        self.assertLessEqual(image.pixelColor(1, 0).red(), 2)
        self.assertGreaterEqual(image.pixelColor(19, 19).red(), 253)
        self.assertAlmostEqual(image.pixelColor(0, 10).red(), 127, delta=2)

    def _rendered(self, layer, size):
        settings = QgsMapSettings()
        settings.setLayers([layer])
        settings.setExtent(layer.extent())
        settings.setOutputSize(QSize(size, size))
        job = QgsMapRendererSequentialJob(settings)
        job.start()
        job.waitForFinished()
        return job.renderedImage()

    def _shapes(self, name, uri, wkts, rows=None):
        layer = QgsVectorLayer(uri, name, "memory")
        self.assertTrue(layer.isValid())
        features = []
        for index, wkt in enumerate(wkts):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            if rows:
                feature.setAttributes(rows[index])
            features.append(feature)
        self.assertTrue(layer.dataProvider().addFeatures(features)[0])
        layer.updateExtents()
        self.project.addMapLayer(layer)
        return layer, [feature.id() for feature in layer.getFeatures()]

    def _check(self, layer_name):
        result = ToolExecutor().run(ToolCall("check", "check_layer", {"layer_name": layer_name}))
        self.assertTrue(result.ok, result.payload)
        json.dumps(result.payload, allow_nan=False)
        return result.payload

    def test_a_bow_tie_polygon_is_reported_invalid_with_its_id(self):
        bow_tie = "POLYGON ((400000 6170000, 400010 6170010, 400010 6170000, 400000 6170010, 400000 6170000))"
        square = "POLYGON ((400020 6170000, 400030 6170000, 400030 6170010, 400020 6170010, 400020 6170000))"
        _, ids = self._shapes("parcels", "Polygon?crs=EPSG:32637", [bow_tie, square])
        payload = self._check("parcels")
        self.assertEqual(payload["problems"], {"invalid_geometry": 1})
        (sample,) = payload["invalid_geometry"]
        self.assertEqual(sample["id"], ids[0])
        self.assertIn("intersection", sample["reason"].lower())
        self.assertIn("native:fixgeometries", payload["suggestions"][0])

    def test_a_repeated_geometry_is_found_whatever_its_start_vertex(self):
        square = "POLYGON ((400000 6170000, 400010 6170000, 400010 6170010, 400000 6170010, 400000 6170000))"
        shifted = "POLYGON ((400010 6170010, 400000 6170010, 400000 6170000, 400010 6170000, 400010 6170010))"
        other = "POLYGON ((400020 6170000, 400030 6170000, 400030 6170010, 400020 6170000))"
        _, ids = self._shapes("plots", "Polygon?crs=EPSG:32637", [square, other, shifted])
        payload = self._check("plots")
        self.assertEqual(payload["problems"], {"duplicate_geometry": 1})
        self.assertEqual(payload["duplicate_geometry_groups"], [[ids[0], ids[2]]])

    def test_a_field_without_values_is_reported_and_gaps_are_counted(self):
        uri = "Point?crs=EPSG:32637&field=name:string&field=note:string&field=kind:string"
        points = ["POINT (400000 6170000)", "POINT (400100 6170100)", "POINT (400200 6170200)"]
        rows = [["a", None, "x"], ["b", None, ""], ["c", None, None]]
        self._shapes("wells", uri, points, rows)
        payload = self._check("wells")
        self.assertEqual(payload["problems"], {"empty_fields": 1})
        self.assertEqual(payload["empty_fields"], ["note"])
        self.assertEqual(payload["missing_values"], {"kind": {"null": 1, "blank": 1}})
        self.assertIn("delete_field", payload["suggestions"][0])

    def test_metres_under_a_geographic_crs_are_suspicious(self):
        points = ["POINT (4000000 6000000)", "POINT (4000100 6000100)"]
        self._shapes("stations", "Point?crs=EPSG:4326", points)
        payload = self._check("stations")
        self.assertEqual(payload["problems"], {"suspicious_coordinates": 1})
        self.assertEqual(payload["data_bounds"]["xmax"], 4000100.0)
        self.assertIn("native:assignprojection", payload["suggestions"][0])
        self.assertIn("Do not reproject", payload["suggestions"][0])

    def test_a_clean_layer_reports_no_problems(self):
        square = "POLYGON ((400000 6170000, 400010 6170000, 400010 6170010, 400000 6170010, 400000 6170000))"
        self._shapes("clean", "Polygon?crs=EPSG:32637&field=name:string", [square], [["ok"]])
        payload = self._check("clean")
        self.assertEqual((payload["problems"], payload["suggestions"]), ({}, []))
        self.assertEqual(
            (payload["checked_features"], payload["geometry"], payload["crs"]), (1, "polygon", "EPSG:32637")
        )
        self.assertNotIn("partial", payload)
        line = get_tool_by_name("check_layer").summarize_result({}, payload)
        self.assertTrue(line.startswith(tr_n("Checked %n feature(s)", 1)), line)

    def test_a_scan_past_the_cap_says_it_is_partial(self):
        points = ["POINT (400000 6170000)", "POINT (400100 6170100)", "POINT (400200 6170200)"]
        self._shapes("many", "Point?crs=EPSG:32637", points)
        with patch.object(quality_scan, "MAX_FEATURES", 2):
            payload = self._check("many")
        self.assertEqual((payload["checked_features"], payload["partial"]), (2, True))
        self.assertIn("of 3", payload["scan_note"])

    def test_no_crs_and_a_project_in_many_crss_are_said(self):
        layer, _ = self._shapes("lost", "Point?crs=EPSG:32637", ["POINT (400000 6170000)"])
        layer.setCrs(QgsCoordinateReferenceSystem())
        self._shapes("wgs", "Point?crs=EPSG:4326", ["POINT (37.6 55.7)"])
        self._shapes("utm", "Point?crs=EPSG:32637", ["POINT (400000 6170000)"])
        payload = self._check("lost")
        self.assertEqual((payload["problems"], payload["crs"]), ({"invalid_crs": 1}, "unknown"))
        self.assertIn("3 different CRSs", payload["project_crs"])
        self.assertIn("native:reprojectlayer", payload["suggestions"][-1])

    def test_a_raster_reports_its_nodata_or_its_absence(self):
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        driver = gdal.GetDriverByName("GTiff")
        for name, nodata in (("declared", -9999.0), ("bare", None)):
            dataset = driver.Create(str(self.root / f"{name}.tif"), 4, 4, 1, gdal.GDT_Float32)
            dataset.SetGeoTransform((37.5, 0.01, 0, 55.8, 0, -0.01))
            dataset.SetProjection(srs.ExportToWkt())
            dataset.GetRasterBand(1).Fill(1.0)
            if nodata is not None:
                dataset.GetRasterBand(1).SetNoDataValue(nodata)
            dataset = None
            self.project.addMapLayer(QgsRasterLayer(str(self.root / f"{name}.tif"), name))
        declared = self._check("declared")
        self.assertEqual((declared["kind"], declared["band_count"], declared["problems"]), ("raster", 1, {}))
        self.assertEqual(declared["nodata_by_band"], [-9999.0])
        self.assertNotIn("nodata_note", declared)
        bare = self._check("bare")
        self.assertEqual((bare["nodata_by_band"], bare["problems"]), ([None], {}))
        self.assertIn("no_data_values", bare["suggestions"][0])

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

    def test_two_unnamed_labels_in_one_batch_both_land_on_the_layout(self):
        self._run("create_layout", name="Sheet", page="a4", orientation="landscape")
        batch = WriteBatch(ToolExecutor())
        for y, text in ((8, "Title"), (30, "Subtitle")):
            label = {"layout_name": "Sheet", "item_type": "label", "x": 10, "y": y, "properties": {"text": text}}
            batch.add(ToolCall(text, "add_layout_item", label))
        results = self._applied(batch)
        self.assertTrue(all(result.ok for result in results), [result.payload for result in results])
        self.assertEqual([result.payload["id"] for result in results], ["label-1", "label-2"])
        layout = self.project.layoutManager().layoutByName("Sheet")
        self.assertEqual(layout.itemById("label-2").text(), "Subtitle")


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
