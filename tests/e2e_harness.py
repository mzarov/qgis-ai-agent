"""Shared harness for whole-plugin scenarios in a live QGIS.

`PluginCase` loads the installed plugin into a bare main window, opens the
dock, builds a small project and drives the chat the way a person does. The
model behind it is up to the subclass: `real_qgis_e2e` points it at the
scripted model, `real_qgis_live` at a real provider.
"""

import faulthandler
import os
import pathlib
import tempfile
import time
import unittest

from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow, QWidget

from ai_agent.core.settings import (
    reset_capabilities,
    set_api_url,
    set_dialect,
    set_model,
    set_reasoning_enabled,
    set_verify_after_apply,
)
from ai_agent.plugin import QgisAiAgentPlugin

SETTLE_S = 0.4
# A test that has not ended by then is stuck, not slow: every thread's stack goes to stderr and
# the process exits, so a hang names its place instead of eating the CI job's whole timeout.
HANG_S = 300
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 760
ARTIFACTS = pathlib.Path(os.environ.get("E2E_ARTIFACTS", "build/e2e"))
DISTRICT_POPULATIONS = [20000 + index * 15000 for index in range(6)]


class _MessageBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def pushMessage(self, title: str, text: str, *args: object, **kwargs: object) -> None:
        self.messages.append(text)


class _Interface(QObject):
    """The part of QgisInterface the plugin touches, the active layer included."""

    currentLayerChanged = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.window = QMainWindow()
        self.bar = _MessageBar()
        self._active = None

    def activeLayer(self) -> object:
        return self._active

    def setActiveLayer(self, layer: object) -> bool:
        self._active = layer
        self.currentLayerChanged.emit(layer)
        return True

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


class WindowSpy(QObject):
    """Widgets shown as windows and then given a parent: each was shown before its layout took it.

    Such a widget becomes a native window, made and torn down for nothing: thirty hint labels once took
    most of the second the settings needed to open. A window a test shows on purpose keeps no parent
    and is not counted.
    """

    def __init__(self) -> None:
        super().__init__()
        self.strays: list[str] = []
        # The widgets themselves, not only their ids: a freed wrapper's id could come back as another's.
        self._windows: dict[int, QWidget] = {}

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.Show and isinstance(watched, QWidget) and watched.parent() is None:
            self._windows[id(watched)] = watched
        elif kind == QEvent.Type.ParentChange and self._windows.pop(id(watched), None) is not None:
            self.strays.append(type(watched).__name__)
        return False


def process() -> None:
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        process()
        time.sleep(0.01)


class PluginCase(unittest.TestCase):
    """One plugin instance and one fresh project per test."""

    api_url = ""
    model_name = ""
    idle_timeout_s = 60

    def setUp(self) -> None:
        faulthandler.dump_traceback_later(HANG_S, exit=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)
        set_api_url(self.api_url)
        set_model(self.model_name)
        set_dialect("openai")
        set_verify_after_apply(True)
        set_reasoning_enabled(False)
        reset_capabilities(self.api_url, self.model_name, "openai")
        self.folder = tempfile.mkdtemp(prefix="ai-agent-e2e-")
        build_project(self.folder)
        self.iface = _Interface()
        self.iface.window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.iface.window.show()
        self.addCleanup(self._close_window)
        self.window_spy = WindowSpy()
        QCoreApplication.instance().installEventFilter(self.window_spy)
        self.plugin = QgisAiAgentPlugin(self.iface)
        self.plugin.initGui()
        self.plugin.run()
        self.orchestrator = self.plugin._orchestrator
        self.dock = self.plugin.dock_widget
        self.destructive: list[list[str]] = []
        self.dock.confirm_destructive = lambda lines, details="": self.destructive.append(list(lines)) or True
        self.orchestrator.on_new_session()

    def tearDown(self) -> None:
        QCoreApplication.instance().removeEventFilter(self.window_spy)
        self.plugin.unload()
        QgsProject.instance().clear()
        pump(0.1)
        self.assertEqual(self.window_spy.strays, [], "widgets shown before they had a parent")

    def _close_window(self) -> None:
        # Freed now, at a quiet moment. Left to Python's cycle collector, the window could go in the middle of
        # a later test's focus change, while Qt still holds it as the previous focus window: a segfault in
        # QApplicationPrivate::notifyActiveWindowChange on QGIS 4.2, whenever the collector happened to run.
        self.iface.window.close()
        self.iface.window.deleteLater()
        pump(0.1)

    @property
    def agent(self):
        return self.orchestrator.agent

    def wait_idle(self) -> None:
        deadline = time.monotonic() + self.idle_timeout_s
        quiet_since = None
        while time.monotonic() < deadline:
            process()
            busy = (
                self.agent.is_running
                or bool(getattr(self.agent, "is_applying", False))
                or self.orchestrator.compaction.is_running
            )
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
        self.assertTrue(self.agent.has_pending_writes, f"nothing was queued to apply; the model said: {self.last()}")
        self.orchestrator.on_confirm_plan()
        self.wait_idle()

    def answers(self) -> list[str]:
        return [str(m["content"]) for m in self.orchestrator.conversation.messages if m["role"] == "assistant"]

    def last(self) -> str:
        answers = self.answers()
        return answers[-1] if answers else ""

    def shot(self, name: str) -> None:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        pump(0.2)
        self.dock.grab().save(str(ARTIFACTS / f"{name}.png"))

    def shot_now(self, name: str, after: float) -> None:
        """A frame `after` seconds on, for a transition caught in the middle."""
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        pump(after)
        self.dock.grab().save(str(ARTIFACTS / f"{name}.png"))

    def layer(self, name: str) -> QgsVectorLayer:
        layers = QgsProject.instance().mapLayersByName(name)
        self.assertEqual(len(layers), 1, f"expected one layer named {name!r}")
        return layers[0]


def build_project(folder: str) -> None:
    """Six square districts with a population field in a GeoPackage, and one river in memory."""
    districts = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=pop2020:integer", "districts", "memory")
    features = []
    for index, population in enumerate(DISTRICT_POPULATIONS):
        x, y = 37.4 + 0.08 * (index % 3), 55.6 + 0.08 * (index // 3)
        feature = QgsFeature(districts.fields())
        feature.setAttributes([f"District {index + 1}", population])
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
