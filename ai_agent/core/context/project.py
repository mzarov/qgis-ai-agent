from contextlib import suppress
from typing import Any

from qgis.core import QgsProject

from ai_agent.qgis_tools.common.layers import (
    active_layer_name,
    crs_authid,
    geometry_type_name,
    layer_kind,
    safe_feature_count,
)

MAX_LISTED = 12
COUNTABLE_PROVIDERS = frozenset({"ogr", "memory", "delimitedtext", "spatialite", "virtual"})
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


def feature_count_if_cheap(layer: Any) -> int | None:
    provider = ""
    with suppress(Exception):
        provider = str(layer.providerType() or "").lower()
    if provider not in COUNTABLE_PROVIDERS:
        return None
    count = safe_feature_count(layer)
    return count if count is not None and count >= 0 else None


def selected_count(layer: Any) -> int:
    with suppress(Exception):
        return int(layer.selectedFeatureCount())
    return 0


def _join_capped(items: list[str]) -> str:
    if len(items) <= MAX_LISTED:
        return ", ".join(items)
    return ", ".join(items[:MAX_LISTED]) + f" and {len(items) - MAX_LISTED} more"
