from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsRectangle

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_READ, BaseTool

WGS84 = "EPSG:4326"
# A point with no scale opens at a town's size: streets readable, the place in context.
DEFAULT_SCALE = 50000
MIN_SCALE = 100
MAX_SCALE = 500_000_000
NEEDS_AREA = 'Give bbox as "west,south,east,north" in degrees, or lon and lat of a point.'


class ZoomToAreaTool(BaseTool):
    name = "zoom_to_area"
    description = (
        "Move the map view to a place: a bounding box in degrees (as geocode returns it), or a point with an "
        "optional scale. Changes the view only, touches neither the project nor the data."
    )
    skill = "project"
    safety = SAFETY_READ
    external_effect = False
    network_access = False
    egress = EGRESS_METADATA
    constraints = [
        "bbox or lon/lat, not both",
        "coordinates in degrees (EPSG:4326); for a named place geocode first or use well-known bounds",
    ]
    examples = ["Zoom to Rotterdam", "Show the Netherlands", "Go to 52.37, 4.89 at 1:10000"]
    params_schema = [
        {
            "name": "bbox",
            "type": "string",
            "description": 'Area as "west,south,east,north" in degrees, e.g. the bbox geocode returned',
            "required": False,
        },
        {"name": "lon", "type": "number", "description": "Longitude of a point to centre on", "required": False},
        {"name": "lat", "type": "number", "description": "Latitude of a point to centre on", "required": False},
        {
            "name": "scale",
            "type": "number",
            "description": f"Map scale denominator for a point, default {DEFAULT_SCALE}",
            "required": False,
        },
        {"name": "place", "type": "string", "description": "Name of the place, for the user", "required": False},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(params)
        has_point = params.get("lon") is not None or params.get("lat") is not None
        if params.get("bbox") and has_point:
            raise ValueError("Give bbox or lon/lat, not both.")
        if params.get("bbox"):
            prepared["bbox"] = ",".join(str(value) for value in parse_bbox(params["bbox"]))
        elif has_point:
            lon, lat = _number(params.get("lon"), "lon", 180), _number(params.get("lat"), "lat", 90)
            prepared.update(lon=lon, lat=lat, scale=_scale(params.get("scale")))
        else:
            raise ValueError(NEEDS_AREA)
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        place = str(params.get("place") or "").strip()
        if place:
            return tr("Moving the map to {0}.").format(place)
        if params.get("lon") is not None and params.get("lat") is not None:
            return tr("Moving the map to {0}, {1}.").format(params.get("lat"), params.get("lon"))
        return tr("Moving the map view.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        prepared = self.prepare(params)
        try:
            from qgis.utils import iface

            canvas = iface.mapCanvas() if iface else None
        except Exception:
            canvas = None
        if canvas is None:
            raise ValueError("The map is not available: the plugin is running without a QGIS window.")
        to_map = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem(WGS84), canvas.mapSettings().destinationCrs(), QgsProject.instance()
        )
        if prepared.get("bbox"):
            west, south, east, north = parse_bbox(prepared["bbox"])
            canvas.setExtent(to_map.transformBoundingBox(QgsRectangle(west, south, east, north)))
        else:
            canvas.setCenter(to_map.transform(QgsPointXY(prepared["lon"], prepared["lat"])))
            canvas.zoomScale(prepared["scale"])
        canvas.refresh()
        return {"scale": round(canvas.scale()), "crs": canvas.mapSettings().destinationCrs().authid()}


def parse_bbox(raw: Any) -> tuple[float, float, float, float]:
    """West, south, east, north in degrees; ValueError with the expected form otherwise."""
    try:
        values = [float(part) for part in str(raw).replace(";", ",").split(",")]
    except ValueError:
        values = []
    if len(values) != 4:
        raise ValueError(f"bbox '{raw}' is not four numbers. {NEEDS_AREA}")
    west, south, east, north = values
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"bbox '{raw}' is not west,south,east,north in degrees with west < east and south < north.")
    return west, south, east, north


def _number(raw: Any, name: str, limit: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number in degrees. {NEEDS_AREA}") from None
    if abs(value) > limit:
        raise ValueError(f"{name} {value} is outside ±{limit}°.")
    return value


def _scale(raw: Any) -> float:
    if raw in (None, ""):
        return float(DEFAULT_SCALE)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("scale must be a number such as 25000 for 1:25000.") from None
    return min(max(value, MIN_SCALE), MAX_SCALE)
