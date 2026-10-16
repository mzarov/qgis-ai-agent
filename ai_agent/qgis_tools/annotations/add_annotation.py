from contextlib import suppress
from typing import Any

from qgis.core import (
    QgsAnnotationMarkerItem,
    QgsAnnotationPointTextItem,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsTextFormat,
)
from qgis.PyQt.QtGui import QColor

from ai_agent.i18n import tr
from ai_agent.qgis_tools.annotations.store import annotation_layer, item_text
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool

KIND_TEXT = "text"
KIND_MARKER = "marker"
KINDS = (KIND_TEXT, KIND_MARKER)
DEFAULT_SIZE = 12.0
MAX_SIZE = 72.0
WGS84 = "EPSG:4326"
# Relative: a point read back after a CRS round trip differs in the last digits, metres or degrees alike.
POSITION_TOLERANCE = 1e-6


class AddAnnotationTool(BaseTool):
    name = "add_annotation"
    description = (
        "Put a note directly on the map: a text label or a marker at given "
        "coordinates. Annotations live in the project's annotation layer, above "
        "all data layers, and are not features — use them to point at things, "
        "not to store data. x is the longitude, y the latitude: a person's "
        "'55.75, 37.62' is latitude first, so x=37.62, y=55.75."
    )
    skill = "annotations"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = [
        "Coordinates are lon/lat in EPSG:4326 unless crs says otherwise",
        "kind is text or marker; text needs the text field",
    ]
    examples = ["Mark the city centre", "Put 'flood zone' over this district"]
    params_schema = [
        {"name": "kind", "type": "string", "enum": sorted(KINDS), "description": "text or marker", "required": True},
        {"name": "x", "type": "number", "description": "Longitude or X", "required": True},
        {"name": "y", "type": "number", "description": "Latitude or Y", "required": True},
        {"name": "text", "type": "string", "description": "The label text (for kind=text)", "required": False},
        {
            "name": "crs",
            "type": "string",
            "description": f"CRS of the coordinates, default {WGS84}",
            "required": False,
        },
        {"name": "size", "type": "number", "description": "Text size in points, default 12", "required": False},
        {"name": "color", "type": "string", "description": "Text or marker colour, e.g. #d02020", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(params)
        prepared["kind"] = _checked_kind(params.get("kind"))
        prepared["x"], prepared["y"] = _checked_xy(params)
        if prepared["kind"] == KIND_TEXT and not str(params.get("text") or "").strip():
            raise ValueError("A text annotation needs the text field.")
        colour = str(params.get("color") or "").strip()
        if colour and not QColor(colour).isValid():
            raise ValueError(f"'{colour}' is not a colour. Use #rrggbb or a colour name.")
        authid = _checked_crs(params.get("crs")).authid()
        prepared["crs"] = authid if isinstance(authid, str) and authid else str(params.get("crs") or WGS84).strip()
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        if str(params.get("kind") or "") == KIND_MARKER:
            return tr("Placing a marker on the map.")
        return tr("Placing a note on the map: {0}").format(str(params.get("text") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        kind = _checked_kind(params.get("kind"))
        x, y = _checked_xy(params)
        layer = annotation_layer()
        point = _to_project_point(x, y, _checked_crs(params.get("crs")))
        if kind == KIND_MARKER:
            item = QgsAnnotationMarkerItem(point)
        else:
            # The text item takes a QgsPointXY: QGIS 4.2 refuses the QgsPoint the marker accepts.
            item = QgsAnnotationPointTextItem(str(params.get("text") or "").strip(), QgsPointXY(point.x(), point.y()))
            _apply_text_look(item, params)
        item_id = layer.addItem(item)
        return {"id": str(item_id), "kind": kind, "note": "The annotation sits above every layer."}

    def confirm_applied(self, params: dict[str, Any], payload: dict[str, Any]) -> bool | None:
        # A note is a fact, not a look: it is on the map, with its words, where it was asked to be.
        item = (annotation_layer().items() or {}).get(str(payload.get("id") or ""))
        if item is None:
            return False
        if _checked_kind(params.get("kind")) == KIND_TEXT and item_text(item) != str(params.get("text") or "").strip():
            return False
        wanted = _to_project_point(*_checked_xy(params), _checked_crs(params.get("crs")))
        centre = item.boundingBox().center()
        return _near(centre.x(), wanted.x()) and _near(centre.y(), wanted.y())


def _near(actual: float, wanted: float) -> bool:
    return abs(actual - wanted) <= POSITION_TOLERANCE * max(1.0, abs(wanted))


def _checked_kind(raw: Any) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"Unknown annotation kind '{raw}'. Available: {', '.join(KINDS)}.")
    return kind


def _checked_xy(params: dict[str, Any]) -> tuple[float, float]:
    try:
        return float(params.get("x")), float(params.get("y"))
    except (TypeError, ValueError):
        raise ValueError("x and y are numbers — longitude and latitude for EPSG:4326.") from None


def _to_project_point(x: float, y: float, source: Any) -> Any:
    point = QgsPoint(x, y)
    project = QgsProject.instance()
    target = project.crs()
    if not target.isValid() or source.authid() == target.authid():
        return point
    try:
        point.transform(QgsCoordinateTransform(source, target, project))
    except Exception as failure:
        raise ValueError(
            f"Could not move ({x}, {y}) from {source.authid()} into the project CRS {target.authid()}: {failure}. "
            "Check that x/y are in the given crs (lon/lat for EPSG:4326)."
        ) from None
    return point


def _checked_crs(raw: Any) -> Any:
    text = str(raw or "").strip() or WGS84
    crs = QgsCoordinateReferenceSystem(text)
    if not crs.isValid():
        raise ValueError(f"Unknown CRS '{text}'. Give an authority id such as EPSG:4326.")
    return crs


def _apply_text_look(item: Any, params: dict[str, Any]) -> None:
    with suppress(Exception):
        text_format = QgsTextFormat()
        text_format.setSize(_size(params.get("size")))
        colour = str(params.get("color") or "").strip()
        if colour:
            text_format.setColor(QColor(colour))
        item.setFormat(text_format)


def _size(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_SIZE
    return max(4.0, min(value, MAX_SIZE))
