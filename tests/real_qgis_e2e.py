"""End-to-end scenarios: the installed plugin, live QGIS, a scripted model.

Each test drives the plugin the way a person does — a request in the chat,
Apply, Stop, undo — while `e2e_model.ScriptedModel` plays the language model
over real HTTP and streaming. Assertions are on what matters to the user: the
project state, what reached the model, and what the chat shows. Screenshots of
the panel land in `E2E_ARTIFACTS` (default `build/e2e`) for a look by eye.

Runs inside `real_qgis_workflows.py` against the extracted plugin ZIP.
"""

import os
import pathlib
import tempfile
import time
import unittest

from e2e_model import ScriptedModel, call, calls, fail, say
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QEventLoop
from qgis.PyQt.QtWidgets import QMainWindow

from ai_agent.core.settings import (
    reset_capabilities,
    set_api_url,
    set_dialect,
    set_model,
    set_verify_after_apply,
)
from ai_agent.plugin import QgisAiAgentPlugin

IDLE_TIMEOUT_S = 60
SETTLE_S = 0.4
MODEL = "scripted-model"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 760
ARTIFACTS = pathlib.Path(os.environ.get("E2E_ARTIFACTS", "build/e2e"))


class _MessageBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def pushMessage(self, title: str, text: str, *args: object, **kwargs: object) -> None:
        self.messages.append(text)


class _Interface:
    def __init__(self) -> None:
        self.window = QMainWindow()
        self.bar = _MessageBar()

    def mainWindow(self) -> QMainWindow:
        return self.window

    def messageBar(self) -> _MessageBar:
        return self.bar

    def addPluginToMenu(self, title: str, action: object) -> None:
        return None

    def removePluginMenu(self, title: str, action: object) -> None:
        return None

    def addToolBarIcon(self, action: object) -> None:
        return None

    def removeToolBarIcon(self, action: object) -> None:
        return None

    def addDockWidget(self, area: object, dock: object) -> None:
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock: object) -> None:
        self.window.removeDockWidget(dock)


def _process() -> None:
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _pump(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _process()
        time.sleep(0.01)


class ScenarioCase(unittest.TestCase):
    def setUp(self) -> None:
        self.model = ScriptedModel().start()
        set_api_url(self.model.url)
        set_model(MODEL)
        set_dialect("openai")
        set_verify_after_apply(True)
        reset_capabilities(self.model.url, MODEL, "openai")
        self.folder = tempfile.mkdtemp(prefix="ai-agent-e2e-")
        _build_project(self.folder)
        self.iface = _Interface()
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.iface.window.show()
        self.plugin = QgisAiAgentPlugin(self.iface)
        self.plugin.initGui()
        self.plugin.run()
        self.orchestrator = self.plugin._orchestrator
        self.dock = self.plugin.dock_widget
        self.destructive: list[list[str]] = []
        self.dock.confirm_destructive = lambda lines, details="": self.destructive.append(list(lines)) or True
        self.orchestrator.on_new_session()

    def tearDown(self) -> None:
        self.plugin.unload()
        self.model.stop()
        QgsProject.instance().clear()
        _pump(0.1)
        self.assertEqual(self.model.unexpected, [], "the plugin sent requests no scenario turn answered")
        self.assertEqual(list(self.model.turns), [], "scripted turns were left unused")

    @property
    def agent(self):
        return self.orchestrator.agent

    def wait_idle(self) -> None:
        deadline = time.monotonic() + IDLE_TIMEOUT_S
        quiet_since = None
        while time.monotonic() < deadline:
            _process()
            busy = self.agent.is_running or bool(getattr(self.agent, "is_applying", False))
            if busy:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= SETTLE_S:
                return
            time.sleep(0.01)
        self.fail("the run did not finish in time")

    def ask(self, text: str) -> None:
        self.orchestrator.on_prompt(text)
        self.wait_idle()

    def apply(self) -> None:
        self.assertTrue(self.agent.has_pending_writes, "nothing was queued to apply")
        self.orchestrator.on_confirm_plan()
        self.wait_idle()

    def answers(self) -> list[str]:
        return [str(m["content"]) for m in self.orchestrator.conversation.messages if m["role"] == "assistant"]

    def shot(self, name: str) -> None:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        _pump(0.2)
        self.dock.grab().save(str(ARTIFACTS / f"{name}.png"))

    def layer(self, name: str) -> QgsVectorLayer:
        layers = QgsProject.instance().mapLayersByName(name)
        self.assertEqual(len(layers), 1, f"expected one layer named {name!r}")
        return layers[0]


class StyleScenario(ScenarioCase):
    def test_style_apply_and_verification(self) -> None:
        self.model.script(
            call("list_layers"),
            call("load_skill", names=["style"]),
            call("set_graduated", layer_name="districts", field="pop2020", classes=5),
            say("I suggest colouring districts by pop2020 in 5 classes."),
            call("describe_style", layer_name="districts"),
            say("Checked: districts is coloured in 5 classes."),
        )
        self.ask("Colour districts by pop2020 in 5 classes")

        first = self.model.tool_names(0)
        for tool in ("list_layers", "describe_layer", "query_layer", "get_field_values", "load_skill"):
            self.assertIn(tool, first, "a tool the model needs was hidden from it")
        listed = self.model.sent_text(1)
        self.assertIn('"geometry": "polygon"', listed.replace('\\"', '"'))
        self.assertIn('"geometry": "line"', listed.replace('\\"', '"'))
        self.assertIn("set_graduated", self.model.tool_names(2))

        self.apply()
        renderer = self.layer("districts").renderer()
        self.assertEqual(renderer.type(), "graduatedSymbol")
        self.assertEqual(renderer.classAttribute(), "pop2020")
        self.assertEqual(len(renderer.ranges()), 5)

        verification = self.model.tool_names(4)
        self.assertIn("describe_style", verification, "verification started without the applying run's skills")
        self.assertIn("Message from the plugin", self.model.sent_text(4))
        self.assertEqual(self.answers()[-1], "Checked: districts is coloured in 5 classes.")
        self.shot("style_apply_verification")


class StopScenario(ScenarioCase):
    def test_stop_keeps_the_partial_answer_and_the_request(self) -> None:
        self.model.script(say("A map projection flattens the surface of the Earth onto a plane. " * 20, 0.05))
        self.orchestrator.on_prompt("Tell me about projections")
        _pump(1.5)
        self.assertTrue(self.agent.is_running)
        self.orchestrator.on_stop()
        self.wait_idle()

        kept = self.answers()
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].startswith("A map projection"))
        self.assertEqual(self.dock.composer._edit.toPlainText(), "Tell me about projections")
        self.shot("stop_keeps_partial")


class UndoScenario(ScenarioCase):
    def test_buffer_recolour_and_undo_keep_scratch_features(self) -> None:
        self.model.script(
            call("load_skill", names=["processing"]),
            calls(
                (
                    "run_processing",
                    {
                        "algorithm_id": "native:reprojectlayer",
                        "parameters": {"INPUT": "Main rivers", "TARGET_CRS": "EPSG:32637"},
                        "output_name": "rivers utm",
                    },
                ),
                (
                    "run_processing",
                    {
                        "algorithm_id": "native:buffer",
                        "parameters": {"INPUT": "rivers utm", "DISTANCE": 500},
                        "output_name": "river buffer",
                    },
                ),
            ),
            say("I suggest reprojecting the river and buffering it by 500 m."),
            say("The buffer is built."),
        )
        self.ask("Buffer Main rivers by 500 m")
        self.apply()
        buffer = self.layer("river buffer")
        self.assertEqual(buffer.featureCount(), 1)
        self.assertEqual(buffer.providerType(), "memory")

        self.model.script(
            call("load_skill", names=["style"]),
            call("set_symbol", layer_name="river buffer", properties={"color": "#0000ff"}),
            say("I suggest recolouring the buffer blue."),
            say("The buffer is blue."),
        )
        before = self.layer("river buffer").renderer().symbol().color().name()
        self.ask("Recolour the buffer blue")
        self.apply()
        self.assertEqual(self.layer("river buffer").renderer().symbol().color().name(), "#0000ff")

        self.model.script(
            call("load_skill", names=["project"]),
            call("undo_last_apply"),
            say("I suggest undoing the last change."),
            say("Undone."),
        )
        self.ask("Undo the last change")
        self.apply()
        self.assertEqual(len(self.destructive), 1, "undo must ask for the destructive confirmation")
        restored = self.layer("river buffer")
        self.assertEqual(restored.featureCount(), 1, "undo emptied a scratch layer")
        self.assertEqual(restored.renderer().symbol().color().name(), before)
        self.shot("buffer_recolour_undo")


class FailureScenario(ScenarioCase):
    def test_a_failed_run_still_offers_the_prepared_steps(self) -> None:
        self.model.script(
            call("load_skill", names=["style"]),
            call("set_opacity", layer_name="districts", opacity=0.5),
            fail(401, "invalid api key"),
        )
        self.ask("Make districts half transparent")
        self.assertTrue(self.agent.has_pending_writes, "the prepared step was thrown away by the error")
        self.assertEqual(self.dock.composer._edit.toPlainText(), "Make districts half transparent")
        self.model.script(say("Opacity applied."))
        self.apply()
        self.assertAlmostEqual(self.layer("districts").opacity(), 0.5)
        self.shot("failure_keeps_plan")


class ComposerScenario(ScenarioCase):
    def test_slash_and_at_popups_insert_what_was_chosen(self) -> None:
        composer = self.dock.composer
        composer._edit.clear()
        composer._edit.insertPlainText("/o")
        _pump(0.1)
        self.assertFalse(composer._popup.isHidden())
        composer._on_complete()
        self.assertEqual(composer._edit.toPlainText(), "/osm ")
        composer._edit.clear()
        composer._edit.insertPlainText("colour @ma")
        _pump(0.1)
        self.assertFalse(composer._popup.isHidden())
        self.shot("mention_popup")
        composer._popup._rows[0].mousePressEvent(None)
        self.assertEqual(composer._edit.toPlainText(), 'colour @"Main rivers" ')


def _build_project(folder: str) -> None:
    districts = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=pop2020:integer", "districts", "memory")
    features = []
    for index in range(6):
        x, y = 37.4 + 0.08 * (index % 3), 55.6 + 0.08 * (index // 3)
        feature = QgsFeature(districts.fields())
        feature.setAttributes([f"District {index + 1}", 20000 + index * 15000])
        ring = [QgsPointXY(x, y), QgsPointXY(x + 0.07, y), QgsPointXY(x + 0.07, y + 0.07), QgsPointXY(x, y + 0.07)]
        feature.setGeometry(QgsGeometry.fromPolygonXY([ring]))
        features.append(feature)
    districts.dataProvider().addFeatures(features)
    path = os.path.join(folder, "districts.gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(districts, path, QgsCoordinateTransformContext(), options)
    QgsProject.instance().addMapLayer(QgsVectorLayer(path, "districts", "ogr"))
    rivers = QgsVectorLayer("LineString?crs=EPSG:4326&field=name:string", "Main rivers", "memory")
    river = QgsFeature(rivers.fields())
    river.setAttributes(["Moskva"])
    river.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(37.4, 55.65), QgsPointXY(37.7, 55.75)]))
    rivers.dataProvider().addFeatures([river])
    QgsProject.instance().addMapLayer(rivers)
    QgsProject.instance().write(os.path.join(folder, "e2e.qgz"))
