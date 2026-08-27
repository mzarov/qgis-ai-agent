import os
from typing import Any

from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsUnitTypes,
)

from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool

MAX_TREE_DEPTH = 6


class GetProjectInfoTool(BaseTool):
    name = "get_project_info"
    description = (
        "Показать проект целиком: название, файл, сохранён ли, систему координат, "
        "единицы измерения, дерево слоёв с группами, порядком и видимостью, "
        "а также темы карты."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["Расскажи про мой проект", "Какие есть группы слоёв?", "Что сейчас видно на карте?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return "Смотрю проект целиком."

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        project = QgsProject.instance()
        title = self._safe(project.title)
        file_path = self._safe(project.fileName)
        return {
            "title": title,
            "display_name": title or self._name_from_path(file_path) or "без имени",
            "file_path": file_path,
            "has_unsaved_changes": bool(self._safe(project.isDirty, default=False)),
            "crs": self._crs(project),
            "distance_units": self._units(project, "distanceUnits"),
            "area_units": self._units(project, "areaUnits"),
            "ellipsoid": self._safe(project.ellipsoid),
            "measurement_note": self._measurement_note(project),
            "layer_tree": self._tree(project),
            "map_themes": self._themes(project),
        }

    @staticmethod
    def _safe(getter: Any, default: str = "") -> Any:
        try:
            return getter() or default
        except Exception:
            return default

    @staticmethod
    def _name_from_path(file_path: str) -> str:
        return os.path.splitext(os.path.basename(file_path or ""))[0]

    @classmethod
    def _measurement_note(cls, project: QgsProject) -> str:
        ellipsoid = cls._safe(project.ellipsoid)
        if ellipsoid and ellipsoid.upper() != "NONE":
            return (
                f"$length и $area считаются по эллипсоиду {ellipsoid} и возвращаются "
                "в единицах проекта, даже если слой хранится в градусах."
            )
        return (
            "Эллипсоид не задан: $length и $area возвращаются в единицах CRS слоя. "
            "Для слоя в градусах такие значения бессмысленны."
        )

    @staticmethod
    def _crs(project: QgsProject) -> dict[str, Any]:
        try:
            crs = project.crs()
            return {
                "authid": crs.authid() or "",
                "description": crs.description() or "",
                "is_geographic": bool(crs.isGeographic()),
            }
        except Exception:
            return {}

    @staticmethod
    def _units(project: QgsProject, getter: str) -> str:
        try:
            return QgsUnitTypes.toString(getattr(project, getter)())
        except Exception:
            return ""

    @classmethod
    def _tree(cls, project: QgsProject) -> list[dict[str, Any]]:
        try:
            root = project.layerTreeRoot()
        except Exception:
            return []
        return cls._nodes(root, depth=0)

    @classmethod
    def _nodes(cls, parent, depth: int) -> list[dict[str, Any]]:
        if depth >= MAX_TREE_DEPTH:
            return []
        result = []
        try:
            children = parent.children()
        except Exception:
            return []
        for node in children:
            entry = cls._node(node, depth)
            if entry:
                result.append(entry)
        return result

    @classmethod
    def _node(cls, node, depth: int) -> dict[str, Any] | None:
        visible = cls._visible(node)
        if isinstance(node, QgsLayerTreeGroup):
            return {
                "kind": "group",
                "name": node.name(),
                "visible": visible,
                "children": cls._nodes(node, depth + 1),
            }
        if isinstance(node, QgsLayerTreeLayer):
            return {"kind": "layer", "name": node.name(), "visible": visible}
        return None

    @staticmethod
    def _visible(node) -> bool:
        try:
            return bool(node.isVisible())
        except Exception:
            return True

    @staticmethod
    def _themes(project: QgsProject) -> list[str]:
        try:
            return list(project.mapThemeCollection().mapThemes())
        except Exception:
            return []
