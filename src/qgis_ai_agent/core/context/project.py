from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.inspect.utils import geometry_type_name, layer_kind

MAX_LISTED = 12


def get_project_context() -> str:
    layers = _describe_layers(QgsProject.instance())
    if not layers:
        return "Слои: нет."
    return "Слои: " + _join_capped(layers) + "."


def _describe_layers(project: QgsProject) -> list[str]:
    described = []
    for layer in project.mapLayers().values():
        name = (layer.name() or "Без имени").strip()
        if layer_kind(layer) == "raster":
            described.append(f"{name} (растр)")
        else:
            described.append(f"{name} ({geometry_type_name(layer) or 'вектор'})")
    return described


def _join_capped(items: list[str]) -> str:
    if len(items) <= MAX_LISTED:
        return ", ".join(items)
    return ", ".join(items[:MAX_LISTED]) + f" и ещё {len(items) - MAX_LISTED}"
