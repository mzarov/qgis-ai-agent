from typing import Any

from qgis.core import (
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)

from qgis_ai_agent.qgis_tools.common.renderers import style_block

COORD_PRECISION = 6
FALLBACK_EXTENT = (0.0, 0.0, 100.0, 100.0)
FALLBACK_CRS = "EPSG:3857"
GEOMETRY_NAMES = ("point", "line", "polygon")


def geometry_type_name(layer: QgsMapLayer) -> str:
    if not isinstance(layer, QgsVectorLayer):
        return ""
    try:
        geometry = str(layer.geometryType()).lower()
    except Exception:
        return "vector"
    for name in GEOMETRY_NAMES:
        if name in geometry:
            return name
    return "vector"


def layer_kind(layer: QgsMapLayer) -> str:
    if isinstance(layer, QgsVectorLayer):
        return "vector"
    if isinstance(layer, QgsRasterLayer):
        return "raster"
    return "other"


def crs_authid(layer: QgsMapLayer) -> str:
    try:
        return layer.crs().authid() or ""
    except Exception:
        return ""


def crs_is_geographic(layer: QgsMapLayer) -> bool:
    try:
        return bool(layer.crs().isGeographic())
    except Exception:
        return False


def crs_units(layer: QgsMapLayer) -> str:
    return "degrees" if crs_is_geographic(layer) else "metres or other linear units"


def suggest_metric_crs(layer: QgsMapLayer) -> str:
    try:
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid() and not project_crs.isGeographic():
            authid = project_crs.authid()
            if authid:
                return authid
    except Exception:
        pass
    return utm_authid(layer)


def utm_authid(layer: QgsMapLayer) -> str:
    try:
        extent = layer.extent()
        longitude = (float(extent.xMinimum()) + float(extent.xMaximum())) / 2.0
        latitude = (float(extent.yMinimum()) + float(extent.yMaximum())) / 2.0
    except Exception:
        return FALLBACK_CRS
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        return FALLBACK_CRS
    zone = max(1, min(60, int((longitude + 180.0) / 6.0) + 1))
    return f"EPSG:{(32600 if latitude >= 0 else 32700) + zone}"


def extent_dict(rectangle) -> dict[str, float] | None:
    if rectangle is None:
        return None
    try:
        if rectangle.isEmpty():
            return None
        return {
            "xmin": round(float(rectangle.xMinimum()), COORD_PRECISION),
            "ymin": round(float(rectangle.yMinimum()), COORD_PRECISION),
            "xmax": round(float(rectangle.xMaximum()), COORD_PRECISION),
            "ymax": round(float(rectangle.yMaximum()), COORD_PRECISION),
        }
    except Exception:
        return None


def safe_extent(layer: QgsMapLayer) -> Any:
    try:
        return layer.extent()
    except Exception:
        return None


def canvas_extent() -> QgsRectangle:
    try:
        from qgis.utils import iface

        if iface and iface.mapCanvas():
            extent = iface.mapCanvas().extent()
            if extent and not extent.isEmpty():
                return extent
    except Exception:
        pass
    for layer in QgsProject.instance().mapLayers().values():
        extent = safe_extent(layer)
        if extent and not extent.isEmpty():
            return extent
    return QgsRectangle(*FALLBACK_EXTENT)


def describe_layer_brief(layer: QgsMapLayer) -> dict[str, Any]:
    kind = layer_kind(layer)
    brief: dict[str, Any] = {
        "id": layer_identifier(layer),
        "name": (layer.name() or "Unnamed").strip(),
        "kind": kind,
        "crs": crs_authid(layer),
        "crs_is_geographic": crs_is_geographic(layer),
    }
    if kind == "vector":
        brief["geometry"] = geometry_type_name(layer)
        feature_count = safe_feature_count(layer)
        if feature_count is not None:
            brief["feature_count"] = feature_count
    brief.update(style_block(layer))
    return brief


def safe_feature_count(layer: QgsMapLayer) -> int | None:
    try:
        return int(layer.featureCount())
    except Exception:
        return None


def find_layer_by_name(name: str) -> QgsMapLayer:
    wanted = (name or "").strip()
    project = QgsProject.instance()
    if wanted:
        matches = project.mapLayersByName(wanted)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise _ambiguous_layer(wanted, matches)
        lowered = wanted.lower()
        insensitive = [
            layer for layer in project.mapLayers().values() if (layer.name() or "").strip().lower() == lowered
        ]
        if len(insensitive) == 1:
            return insensitive[0]
        if len(insensitive) > 1:
            raise _ambiguous_layer(wanted, insensitive)
    available = [_layer_reference(layer) for layer in project.mapLayers().values()]
    hint = ", ".join(available) if available else "the project has no layers"
    raise ValueError(f"Layer not found: '{wanted}'. Available layers: {hint}.")


def find_layer_by_id(layer_id: str) -> QgsMapLayer:
    wanted = (layer_id or "").strip()
    if not wanted:
        raise ValueError("layer_id is empty — use the id returned by list_layers.")
    project = QgsProject.instance()
    try:
        layers = project.mapLayers()
    except Exception:
        layers = {}
    layer = layers.get(wanted)
    if layer is not None:
        return layer
    available = [_layer_reference(item) for item in project.mapLayers().values()]
    hint = ", ".join(available) if available else "the project has no layers"
    raise ValueError(f"Layer id not found: '{wanted}'. Available layers: {hint}.")


def layer_identifier(layer: QgsMapLayer) -> str:
    try:
        identifier = layer.id()
    except Exception:
        return ""
    return identifier if isinstance(identifier, str) else ""


def bind_layer_reference(params: dict[str, Any], layer: QgsMapLayer) -> dict[str, Any]:
    prepared = dict(params)
    prepared["layer_name"] = (layer.name() or "").strip()
    identifier = layer_identifier(layer)
    if identifier:
        prepared["layer_id"] = identifier
    return prepared


def _ambiguous_layer(name: str, matches: list[QgsMapLayer]) -> ValueError:
    choices = ", ".join(_layer_reference(layer) for layer in matches)
    return ValueError(
        f"Layer name '{name}' is ambiguous: {len(matches)} project layers match ({choices}). "
        "Use layer_id from list_layers for a stable target."
    )


def _layer_reference(layer: QgsMapLayer) -> str:
    name = (layer.name() or "Unnamed").strip()
    identifier = layer_identifier(layer)
    return f"'{name}' [id={identifier}]" if identifier else f"'{name}'"
