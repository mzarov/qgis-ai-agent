from qgis.core import QgsProject

from ai_agent.qgis_tools.common.layers import geometry_type_name, layer_kind

MAX_LISTED = 12


def get_project_context() -> str:
    layers = _describe_layers(QgsProject.instance())
    if not layers:
        return "Layers: none."
    return "Layers: " + _join_capped(layers) + "."


def _describe_layers(project: QgsProject) -> list[str]:
    described = []
    for layer in project.mapLayers().values():
        name = (layer.name() or "Unnamed").strip()
        if layer_kind(layer) == "raster":
            described.append(f"{name} (raster)")
        else:
            described.append(f"{name} ({geometry_type_name(layer) or 'vector'})")
    return described


def _join_capped(items: list[str]) -> str:
    if len(items) <= MAX_LISTED:
        return ", ".join(items)
    return ", ".join(items[:MAX_LISTED]) + f" and {len(items) - MAX_LISTED} more"
