from qgis.core import QgsProject

from qgis_ai_agent.qgis_tools.inspect.utils import geometry_type_name, layer_kind

# Стартовая подсказка держится короткой: детали агент добирает read-тулами.
MAX_LISTED = 12


def get_project_context() -> str:
    """
    Краткая сводка о проекте для системного промпта.
    Это только отправная точка — точные данные агент получает через inspect-тулы.
    """
    project = QgsProject.instance()
    return " ".join([_layouts_line(project), _layers_line(project)])


def _layouts_line(project: QgsProject) -> str:
    """Строка со списком макетов проекта."""
    names = [layout.name() for layout in project.layoutManager().layouts()]
    if not names:
        return "Макеты: нет."
    return "Макеты: " + _join_capped(names) + "."


def _layers_line(project: QgsProject) -> str:
    """Строка со списком слоёв и их типами."""
    described = []
    for layer in project.mapLayers().values():
        name = (layer.name() or "Без имени").strip()
        if layer_kind(layer) == "raster":
            described.append(f"{name} (растр)")
        else:
            geometry = geometry_type_name(layer) or "вектор"
            described.append(f"{name} ({geometry})")
    if not described:
        return "Слои: нет."
    return "Слои: " + _join_capped(described) + "."


def _join_capped(items: list[str]) -> str:
    """Склеивает список, обрезая хвост при большом числе элементов."""
    if len(items) <= MAX_LISTED:
        return ", ".join(items)
    rest = len(items) - MAX_LISTED
    return ", ".join(items[:MAX_LISTED]) + f" и ещё {rest}"
