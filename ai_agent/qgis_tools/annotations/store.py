from contextlib import suppress
from typing import Any

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

WGS84 = "EPSG:4326"
COORD_DECIMALS = 6


def annotation_layer() -> Any:
    layer = QgsProject.instance().mainAnnotationLayer()
    if layer is None:
        raise ValueError("This QGIS build has no main annotation layer.")
    return layer


def annotation_crs() -> Any:
    # A layer holding items keeps its CRS when the project's changes: its coordinates are in its own.
    with suppress(Exception):
        crs = annotation_layer().crs()
        if crs.isValid():
            return crs
    return QgsProject.instance().crs()


def list_items() -> list[dict[str, Any]]:
    layer = annotation_layer()
    to_wgs84 = _to_wgs84()
    described = []
    for item_id, item in (layer.items() or {}).items():
        entry: dict[str, Any] = {"id": str(item_id), "kind": type(item).__name__, "text": item_text(item)}
        with suppress(Exception):
            centre = item.boundingBox().center()
            if to_wgs84 is not None:
                centre = to_wgs84.transform(centre)
            entry["lon"], entry["lat"] = round(centre.x(), COORD_DECIMALS), round(centre.y(), COORD_DECIMALS)
        described.append(entry)
    return described


def require_item(item_id: str) -> None:
    items = annotation_layer().items() or {}
    if item_id not in items:
        known = ", ".join(str(key) for key in items) or "the layer holds no annotations"
        raise ValueError(f"No annotation with id '{item_id}'. Available: {known}.")


def remove_item(item_id: str) -> None:
    require_item(item_id)
    annotation_layer().removeItem(item_id)


def item_text(item: Any) -> str:
    try:
        return str(item.text())
    except Exception:
        return ""


def _to_wgs84() -> Any:
    crs = annotation_crs()
    if not crs.isValid() or crs.authid() == WGS84:
        return None
    return QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem(WGS84), QgsProject.instance())
