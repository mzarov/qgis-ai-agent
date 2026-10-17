"""A place picked on the map for the request: a point clicked or an area dragged.

The composer's + menu asks for one; the canvas gets a map tool for that single
pick and has its previous tool back afterwards. The place goes into the request
as text the model reads, in EPSG:4326 degrees and in the order the prompt
explains: `@point(lon, lat)` or `@area(west, south, east, north)`. Typing
coordinates by hand was the alternative, and the model guessing which number is
the latitude.
"""

from contextlib import suppress
from typing import Any

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMessageLog,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolExtent
from qgis.PyQt.QtCore import QObject, pyqtSignal

POINT = "point"
AREA = "area"
WGS84 = "EPSG:4326"
DECIMALS = 5
LOG_TAG = "AI Agent"


def point_text(longitude: float, latitude: float) -> str:
    return f"@point({longitude:.{DECIMALS}f}, {latitude:.{DECIMALS}f})"


def area_text(west: float, south: float, east: float, north: float) -> str:
    return f"@area({west:.{DECIMALS}f}, {south:.{DECIMALS}f}, {east:.{DECIMALS}f}, {north:.{DECIMALS}f})"


class MapPicker(QObject):
    """One pick at a time; `picked` carries the request text, `ended` follows every pick and every cancel."""

    picked = pyqtSignal(str)
    ended = pyqtSignal()

    def __init__(self, iface: Any) -> None:
        super().__init__()
        self._iface = iface
        self._tool: Any = None
        self._previous: Any = None

    @property
    def active(self) -> bool:
        return self._tool is not None

    def start(self, kind: str) -> None:
        self.cancel()
        canvas = self._canvas()
        if canvas is None:
            self.ended.emit()
            return
        self._previous = canvas.mapTool()
        if kind == AREA:
            tool = QgsMapToolExtent(canvas)
            tool.extentChanged.connect(self._area)
        else:
            tool = QgsMapToolEmitPoint(canvas)
            tool.canvasClicked.connect(self._point)
        # Another tool chosen in QGIS ends the pick: the user moved on.
        tool.deactivated.connect(self._deactivated)
        self._tool = tool
        canvas.setMapTool(tool)

    def cancel(self) -> None:
        if self._tool is None:
            return
        self._restore()
        self.ended.emit()

    def _point(self, point: Any, _button: Any = None) -> None:
        try:
            place = self._to_wgs84().transform(point)
        except Exception as error:
            self._failed(error)
            return
        self._finish(point_text(place.x(), place.y()))

    def _area(self, extent: QgsRectangle) -> None:
        if extent.isEmpty():
            return
        try:
            box = self._to_wgs84().transformBoundingBox(extent)
        except Exception as error:
            self._failed(error)
            return
        self._finish(area_text(box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))

    def _finish(self, text: str) -> None:
        self._restore()
        self.picked.emit(text)
        self.ended.emit()

    def _failed(self, error: Exception) -> None:
        QgsMessageLog.logMessage(f"Picking a place on the map failed: {error}", LOG_TAG, Qgis.MessageLevel.Warning)
        self.cancel()

    def _deactivated(self) -> None:
        if self._tool is not None:
            # Deactivated by QGIS itself: do not hand back a tool over the one the user chose.
            self._previous = None
            self.cancel()

    def _restore(self) -> None:
        tool, previous = self._tool, self._previous
        self._tool, self._previous = None, None
        canvas = self._canvas()
        if tool is None or canvas is None:
            return
        with suppress(TypeError, RuntimeError):
            tool.deactivated.disconnect(self._deactivated)
        if canvas.mapTool() is tool:
            if previous is not None:
                canvas.setMapTool(previous)
            else:
                canvas.unsetMapTool(tool)
        tool.deleteLater()

    def _canvas(self) -> Any:
        try:
            return self._iface.mapCanvas()
        except Exception:
            return None

    def _to_wgs84(self) -> QgsCoordinateTransform:
        source = self._canvas().mapSettings().destinationCrs()
        return QgsCoordinateTransform(source, QgsCoordinateReferenceSystem(WGS84), QgsProject.instance())
