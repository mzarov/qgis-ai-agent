import os
from typing import Any

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from ai_agent.core.llm.client import is_local
from ai_agent.core.orchestrator.planning import LAYER_ARGUMENT
from ai_agent.core.settings import get_api_key, get_api_url
from ai_agent.i18n import tr, tr_n
from ai_agent.qgis_tools.common.layers import with_layer_names
from ai_agent.qgis_tools.registry import get_tool_by_name

STYLE_SKILL = "style"


def compact_number(value: int) -> str:
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}k"


def where_to_look(results: list) -> str:
    names = [result.payload.get("result_layer_name") for result in results if result.payload.get("result_layer_name")]
    if names:
        return " " + tr("New layers: {0}.").format(", ".join(f"«{name}»" for name in names))
    if any("outputs" in result.payload for result in results):
        return " " + tr("The result is in the layer panel.")
    return ""


def applied_summary(results: list) -> str:
    """The status line's few words on what an apply changed: the new layer, the layer redrawn, or how much."""
    done = [result for result in results if result.ok]
    if not done:
        return ""
    created = [str(name) for result in done if (name := result.payload.get("result_layer_name"))]
    if len(created) == 1:
        return tr("New layer “{0}”").format(created[0])
    if created:
        return tr_n("%n new layer(s)", len(created))
    layers = {name for result in done if (name := _layer_of(result))}
    if len(layers) == 1:
        restyled = all(getattr(get_tool_by_name(result.call.name), "skill", "") == STYLE_SKILL for result in done)
        wording = tr("Layer “{0}” redrawn") if restyled else tr("Layer “{0}” changed")
        return wording.format(layers.pop())
    if layers:
        return tr_n("%n layer(s) changed", len(layers))
    return tr_n("%n change(s) applied", len(done))


def _layer_of(result: Any) -> str:
    # Queued calls are pinned to layer ids; the person reads the name.
    arguments = with_layer_names(getattr(result.call, "arguments", None) or {})
    name = arguments.get(LAYER_ARGUMENT) if isinstance(arguments, dict) else None
    return name.strip() if isinstance(name, str) else ""


def interrupted_outcome(results: list) -> str:
    successful = [result for result in results if result.ok]
    if not successful:
        return ""
    return tr_n(
        "Stopped after %n completed step(s); pending steps were cancelled.{0}",
        len(successful),
    ).format(where_to_look(successful))


def is_configured() -> bool:
    try:
        url = (get_api_url() or "").strip()
        return bool(url) and (bool((get_api_key() or "").strip()) or is_local(url))
    except Exception:
        return False


def active_layer_chip(iface: Any) -> tuple[str, str]:
    """The active layer for the composer's chip: its name and what it holds; empty strings without one."""
    try:
        layer = iface.activeLayer()
        if layer is None:
            return "", ""
        name = str(layer.name())
        if isinstance(layer, QgsVectorLayer):
            count = int(layer.featureCount())
            return name, tr_n("%n feature(s)", count) if count >= 0 else ""
        if isinstance(layer, QgsRasterLayer):
            return name, tr("raster")
    except Exception:
        return "", ""
    return name, ""


def project_line() -> str:
    """The open project for the welcome card: its file, the number of layers, the CRS; "" when unreadable."""
    try:
        project = QgsProject.instance()
        name = os.path.basename(project.fileName() or "") or tr("Unsaved project")
        parts = [name, tr_n("%n layer(s)", len(project.mapLayers()))]
        crs = project.crs()
        if crs.isValid():
            parts.append(crs.authid())
    except Exception:
        return ""
    return " · ".join(str(part) for part in parts)
