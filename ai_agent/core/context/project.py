from contextlib import suppress
from typing import Any

from qgis.core import QgsProject, QgsUnitTypes

from ai_agent.qgis_tools.common.layers import (
    active_layer_name,
    crs_authid,
    feature_count_if_cheap,
    field_type_name,
    geometry_type_name,
    layer_kind,
    project_metric_crs,
)

MAX_LISTED = 12
NO_LAYERS = "Layers: none."
NO_ELLIPSOID = "NONE"
MEASURED = "Measurements: ellipsoid {0}; $length in {1}, $area in {2}, even on layers in degrees."
UNMEASURED = "Measurements: no ellipsoid; $length and $area are in layer CRS units (degrees on a geographic layer)."
# Without the CRS named, a model reaches for EPSG:3857 to get metres, and its areas come out threefold at 55° N.
METRIC_FALLBACK = " For metres, transform the geometry to {0} first; EPSG:3857 inflates sizes."
# Field names in the context spare most tasks their first describe_layer turn; a wide table lists its first ones.
MAX_CONTEXT_FIELDS = 15


def get_project_context() -> str:
    project = QgsProject.instance()
    lines = []
    crs = project_crs(project)
    if crs:
        lines.append(f"Project CRS: {crs}.")
    active = active_layer_name()
    if active:
        lines.append(f"Active layer: {active}.")
    layers = [context_line(layer) for layer in project.mapLayers().values()]
    if layers:
        # How sizes come out, so a question about lengths or areas needs no get_project_info first.
        measurement = measurement_line(project)
        if measurement:
            lines.append(measurement)
    lines.append("Layers: " + _join_capped(layers) + "." if layers else NO_LAYERS)
    return "\n".join(lines)


def measurement_line(project: Any) -> str:
    """The ellipsoid and units $length and $area use, in unit codes the model reads (not translated names)."""
    try:
        ellipsoid = str(project.ellipsoid() or "").strip()
        if not ellipsoid or ellipsoid.upper() == NO_ELLIPSOID:
            metric = project_metric_crs(project)
            return UNMEASURED + (METRIC_FALLBACK.format(metric) if metric else "")
        distance = QgsUnitTypes.encodeUnit(project.distanceUnits())
        area = QgsUnitTypes.encodeUnit(project.areaUnits())
    except Exception:
        return ""
    return MEASURED.format(ellipsoid, distance, area)


def project_crs(project: Any) -> str:
    with suppress(Exception):
        authid = project.crs().authid()
        return authid.strip() if isinstance(authid, str) else ""
    return ""


def context_line(layer: Any) -> str:
    """The layer's line for the model: the facts of describe_layer_line plus its fields and their types."""
    line = describe_layer_line(layer)
    fields = field_list(layer)
    return f"{line[:-1]}; fields: {fields})" if fields and line.endswith(")") else line


def field_list(layer: Any) -> str:
    """`name:String, pop2020:Integer64` — the first MAX_CONTEXT_FIELDS fields, and how many more there are."""
    if layer_kind(layer) == "raster":
        return ""
    try:
        fields = list(layer.fields())
    except Exception:
        return ""
    shown = ", ".join(f"{field.name()}:{field_type_name(field)}" for field in fields[:MAX_CONTEXT_FIELDS])
    hidden = len(fields) - MAX_CONTEXT_FIELDS
    return f"{shown} and {hidden} more" if hidden > 0 else shown


def describe_layer_line(layer: Any) -> str:
    name = (layer.name() or "Unnamed").strip()
    kind = layer_kind(layer)
    facts = ["raster" if kind == "raster" else (geometry_type_name(layer) or "vector")]
    crs = crs_authid(layer)
    if crs:
        facts.append(crs)
    if kind != "raster":
        count = feature_count_if_cheap(layer)
        if count is not None:
            facts.append(f"{count} feature" if count == 1 else f"{count} features")
        selected = selected_count(layer)
        if selected:
            facts.append(f"{selected} selected")
    return f"{name} ({', '.join(facts)})"


def selected_count(layer: Any) -> int:
    with suppress(Exception):
        return int(layer.selectedFeatureCount())
    return 0


def _join_capped(items: list[str]) -> str:
    if len(items) <= MAX_LISTED:
        return ", ".join(items)
    return ", ".join(items[:MAX_LISTED]) + f" and {len(items) - MAX_LISTED} more"


LAYER_ORIGIN = "layer"


def layer_choices() -> list[tuple[str, str, str]]:
    """Layers for the composer's @ list: name, a short description, origin."""
    choices = []
    with suppress(Exception):
        for layer in QgsProject.instance().mapLayers().values():
            name = (layer.name() or "").strip()
            if name:
                line = describe_layer_line(layer)
                choices.append((name, line[len(name) :].strip(" ()"), LAYER_ORIGIN))
    return sorted(choices, key=lambda item: item[0].casefold())
