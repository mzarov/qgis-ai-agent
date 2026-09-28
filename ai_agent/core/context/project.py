from contextlib import suppress
from typing import Any

from qgis.core import QgsProject

from ai_agent.qgis_tools.common.layers import (
    active_layer_name,
    crs_authid,
    feature_count_if_cheap,
    geometry_type_name,
    layer_kind,
)

MAX_LISTED = 12
NO_LAYERS = "Layers: none."


def get_project_context() -> str:
    project = QgsProject.instance()
    lines = []
    crs = project_crs(project)
    if crs:
        lines.append(f"Project CRS: {crs}.")
    active = active_layer_name()
    if active:
        lines.append(f"Active layer: {active}.")
    layers = [describe_layer_line(layer) for layer in project.mapLayers().values()]
    lines.append("Layers: " + _join_capped(layers) + "." if layers else NO_LAYERS)
    return "\n".join(lines)


def project_crs(project: Any) -> str:
    with suppress(Exception):
        authid = project.crs().authid()
        return authid.strip() if isinstance(authid, str) else ""
    return ""


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
            facts.append(f"{count} features")
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
