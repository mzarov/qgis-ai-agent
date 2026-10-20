from collections import Counter
from contextlib import suppress
from typing import Any

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)

from ai_agent.qgis_tools.common.renderers import style_block

COORD_PRECISION = 6
FALLBACK_EXTENT = (0.0, 0.0, 100.0, 100.0)
FALLBACK_CRS = "EPSG:3857"
WGS84 = "EPSG:4326"
# World projections distort sizes (Web Mercator triples areas at 55° N): never measure in them.
WORLD_PROJECTIONS = frozenset({"merc", "eqc", "robin", "moll", "eck4", "natearth", "wintri", "igh"})
GEOMETRY_NAMES = ("point", "line", "polygon")
LAYER_PINS_KEY = "_ai_agent_layer_pins"
# Remote featureCount() may run COUNT(*) on the main thread, or answer -1.
COUNTABLE_PROVIDERS = frozenset({"ogr", "memory", "delimitedtext", "spatialite", "virtual"})
NOT_COUNTED_NOTE = "Features are not counted for remote sources; use query_layer with aggregate=count."


def enum_name(value: Any) -> str:
    # A Qt6 enum member is an IntEnum: str() gives its number, only `.name` is the word.
    name = getattr(value, "name", "")
    if isinstance(name, str) and name:
        return name
    return str(value).split(".")[-1]


def field_type_name(field: Any) -> str:
    try:
        name = field.typeName()
    except Exception:
        name = ""
    if name:
        return str(name)
    try:
        return enum_name(field.type()).lstrip("Q").lower()
    except Exception:
        return ""


def geometry_type_name(layer: QgsMapLayer) -> str:
    if not isinstance(layer, QgsVectorLayer):
        return ""
    try:
        kind = layer.geometryType()
    except Exception:
        return "vector"
    geometry = enum_name(kind).lower()
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
    authid = local_project_crs(QgsProject.instance())
    if authid and _within_area_of_use(layer, authid):
        return authid
    return utm_authid(layer)


def local_project_crs(project: Any) -> str:
    with suppress(Exception):
        crs = project.crs()
        if crs.isValid() and not crs.isGeographic() and str(crs.projectionAcronym()).lower() not in WORLD_PROJECTIONS:
            return str(crs.authid() or "")
    return ""


def project_metric_crs(project: Any) -> str:
    authid = local_project_crs(project)
    try:
        layers = list(project.mapLayers().values())
    except Exception:
        return authid
    local = [layer for layer in layers if isinstance(layer, QgsVectorLayer)]
    local += [layer for layer in layers if isinstance(layer, QgsRasterLayer) and layer.providerType() == "gdal"]
    # Null, not empty: one point's extent is empty and still says where the layer is.
    placed = [layer for layer in local if _has_extent(layer)]
    if authid and all(_within_area_of_use(layer, authid, project) for layer in placed):
        return authid
    for layer in placed:
        with suppress(Exception):
            centre = wgs84_extent(layer, project).center()
            return utm_at(float(centre.x()), float(centre.y()))
    return authid


def wgs84_extent(layer: QgsMapLayer, project: Any = None) -> Any:
    extent = layer.extent()
    with suppress(Exception):
        crs = layer.crs()
        if crs.isValid() and crs.authid() != WGS84:
            context = project if project is not None else QgsProject.instance()
            transform = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem(WGS84), context)
            return transform.transformBoundingBox(extent)
    return extent


def _has_extent(layer: QgsMapLayer) -> bool:
    try:
        return not layer.extent().isNull()
    except Exception:
        return False


def _within_area_of_use(layer: QgsMapLayer, authid: str, project: Any = None) -> bool:
    # A national grid or a UTM zone distorts far outside its area: Tokyo measured in zone 33N nearly doubles.
    try:
        bounds = QgsCoordinateReferenceSystem(authid).bounds()
        if bounds.isNull() or bounds.isEmpty() or not _has_extent(layer):
            return True
        return bool(bounds.contains(wgs84_extent(layer, project)))
    except Exception:
        return True


def utm_authid(layer: QgsMapLayer) -> str:
    try:
        extent = wgs84_extent(layer)
        longitude = (float(extent.xMinimum()) + float(extent.xMaximum())) / 2.0
        latitude = (float(extent.yMinimum()) + float(extent.yMaximum())) / 2.0
    except Exception:
        return FALLBACK_CRS
    return utm_at(longitude, latitude) or FALLBACK_CRS


def utm_at(longitude: float, latitude: float) -> str:
    if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
        return ""
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
    with suppress(Exception):
        from qgis.utils import iface

        if iface and iface.mapCanvas():
            extent = iface.mapCanvas().extent()
            if extent and not extent.isEmpty():
                return extent
    for layer in QgsProject.instance().mapLayers().values():
        extent = safe_extent(layer)
        if extent and not extent.isEmpty():
            return extent
    return QgsRectangle(*FALLBACK_EXTENT)


def active_layer_name() -> str:
    with suppress(Exception):
        from qgis.utils import iface

        layer = iface.activeLayer() if iface else None
        name = layer.name() if layer is not None else ""
        return name.strip() if isinstance(name, str) else ""
    return ""


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
        brief.update(feature_count_block(layer))
    brief.update(style_block(layer))
    return brief


def safe_feature_count(layer: QgsMapLayer) -> int | None:
    try:
        return int(layer.featureCount())
    except Exception:
        return None


def feature_count_if_cheap(layer: QgsMapLayer) -> int | None:
    provider = ""
    with suppress(Exception):
        provider = str(layer.providerType() or "").lower()
    if provider not in COUNTABLE_PROVIDERS:
        return None
    count = safe_feature_count(layer)
    return count if count is not None and count >= 0 else None


def feature_count_block(layer: QgsMapLayer, key: str = "feature_count") -> dict[str, Any]:
    count = feature_count_if_cheap(layer)
    if count is None:
        return {f"{key}_note": NOT_COUNTED_NOTE}
    return {key: count}


def layer_reference(layer: QgsMapLayer) -> dict[str, str]:
    reference = {"layer_name": (layer.name() or "").strip()}
    identifier = layer_identifier(layer)
    if identifier:
        reference["layer_id"] = identifier
    return reference


def find_layer_by_name(name: str) -> QgsMapLayer:
    wanted = (name or "").strip()
    project = QgsProject.instance()
    if wanted:
        by_id = _layer_with_id(project, wanted)
        if by_id is not None:
            return by_id
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


def _layer_with_id(project: QgsProject, identifier: str) -> QgsMapLayer | None:
    try:
        layers = project.mapLayers()
    except Exception:
        return None
    return layers.get(identifier) if isinstance(layers, dict) else None


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


def validate_public_layer_references(params: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(params)
    prepared.pop(LAYER_PINS_KEY, None)
    layer_name = str(prepared.get("layer_name") or "").strip()
    layer_id = str(prepared.get("layer_id") or "").strip()
    if layer_name and layer_id:
        _resolve_layer_reference(layer_name, layer_id)
    return prepared


def pin_layer_references(params: dict[str, Any]) -> dict[str, Any]:
    prepared = validate_public_layer_references(params)
    pins: list[dict[str, str]] = []
    layer_name = str(prepared.get("layer_name") or "").strip()
    layer_id = str(prepared.get("layer_id") or "").strip()
    if layer_name or layer_id:
        layer = _resolve_layer_reference(layer_name, layer_id)
        identifier = layer_identifier(layer)
        if identifier:
            pins.append({"name": (layer.name() or "").strip(), "id": identifier})
    raw_names = prepared.get("layer_names")
    if isinstance(raw_names, (list, tuple)):
        for raw_name in raw_names:
            name = str(raw_name or "").strip()
            if not name:
                continue
            layer = find_layer_by_name(name)
            identifier = layer_identifier(layer)
            if identifier:
                pins.append({"name": (layer.name() or "").strip(), "id": identifier})
    if pins:
        prepared[LAYER_PINS_KEY] = pins
    return prepared


def layer_pin_error(params: dict[str, Any]) -> str:
    raw_pins = params.get(LAYER_PINS_KEY)
    if not isinstance(raw_pins, list):
        return ""
    try:
        layers = QgsProject.instance().mapLayers()
    except Exception:
        layers = {}
    for pin in raw_pins:
        if not isinstance(pin, dict):
            return "A planned layer target became invalid before apply. Nothing was run."
        name = str(pin.get("name") or "").strip()
        identifier = str(pin.get("id") or "").strip()
        layer = layers.get(identifier)
        current_name = str(layer.name() or "").strip() if layer is not None else ""
        if layer is None or current_name != name:
            shown = name or identifier or "unknown"
            return f"The planned target layer '{shown}' changed or disappeared before apply. Nothing was run."
    return ""


def layer_names_by_id() -> dict[str, str]:
    try:
        layers = QgsProject.instance().mapLayers()
    except Exception:
        return {}
    return {identifier: str(layer.name() or "").strip() for identifier, layer in layers.items()}


def follow_batch_renames(params: dict[str, Any], names_at_start: dict[str, str]) -> dict[str, Any]:
    raw_pins = params.get(LAYER_PINS_KEY)
    if not isinstance(raw_pins, list):
        return params
    current = layer_names_by_id()
    renames: dict[str, str] = {}
    for pin in raw_pins:
        if not isinstance(pin, dict):
            continue
        identifier = str(pin.get("id") or "")
        planned = str(pin.get("name") or "").strip()
        now = current.get(identifier, "")
        if now and now != planned and names_at_start.get(identifier) == planned:
            renames[planned] = now
    if not renames:
        return params
    followed = dict(params)
    followed[LAYER_PINS_KEY] = [
        {**pin, "name": renames.get(str(pin.get("name") or "").strip(), pin.get("name"))}
        if isinstance(pin, dict)
        else pin
        for pin in raw_pins
    ]
    name = str(params.get("layer_name") or "").strip()
    if name in renames:
        followed["layer_name"] = renames[name]
    if isinstance(params.get("layer_names"), (list, tuple)):
        followed["layer_names"] = [renames.get(str(item or "").strip(), item) for item in params["layer_names"]]
    return followed


def with_layer_names(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        return params
    try:
        names = _distinct_names_by_id()
        if not names:
            return params
        return {key: value if str(key).startswith("_") else _named(value, names) for key, value in params.items()}
    except Exception:
        return params


def _distinct_names_by_id() -> dict[str, str]:
    names = layer_names_by_id()
    uses = Counter(names.values())
    return {identifier: name for identifier, name in names.items() if name and uses[name] == 1}


def _named(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, str):
        return names.get(value.strip(), value)
    if isinstance(value, dict):
        return {key: _named(item, names) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_named(item, names) for item in value]
    return value


def pinned_ids(params: dict[str, Any]) -> list[str]:
    raw_pins = params.get(LAYER_PINS_KEY)
    if not isinstance(raw_pins, list):
        return []
    return [str(pin.get("id") or "") for pin in raw_pins if isinstance(pin, dict)]


def pinned_layer(params: dict[str, Any]) -> QgsMapLayer | None:
    identifiers = pinned_ids(params)
    if not identifiers or not identifiers[0]:
        return None
    try:
        return QgsProject.instance().mapLayer(identifiers[0])
    except Exception:
        return None


def _resolve_layer_reference(layer_name: str, layer_id: str) -> QgsMapLayer:
    if layer_id:
        layer = find_layer_by_id(layer_id)
        actual_name = (layer.name() or "").strip()
        if layer_name and actual_name.casefold() != layer_name.casefold():
            raise ValueError(
                f"layer_name '{layer_name}' and layer_id '{layer_id}' identify different layers. "
                "Use a matching name and id from list_layers."
            )
        return layer
    return find_layer_by_name(layer_name)


def _ambiguous_layer(name: str, matches: list[QgsMapLayer]) -> ValueError:
    choices = ", ".join(_layer_reference(layer) for layer in matches)
    return ValueError(
        f"Layer name '{name}' is ambiguous: {len(matches)} project layers match ({choices}). "
        "Pass the layer id from list_layers as layer_name (or as layer_id where the tool has it)."
    )


def _layer_reference(layer: QgsMapLayer) -> str:
    name = (layer.name() or "Unnamed").strip()
    identifier = layer_identifier(layer)
    return f"'{name}' [id={identifier}]" if identifier else f"'{name}'"
