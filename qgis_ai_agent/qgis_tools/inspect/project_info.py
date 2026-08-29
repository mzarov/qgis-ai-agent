import os
from typing import Any

from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsUnitTypes,
)

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, BaseTool

MAX_TREE_DEPTH = 6


class GetProjectInfoTool(BaseTool):
    name = "get_project_info"
    description = (
        "Show the project as a whole: title, file, whether it is saved, coordinate "
        "system, measurement units, the layer tree with groups, order and visibility, "
        "and the map themes."
    )
    skill = "inspect"
    safety = SAFETY_READ
    examples = ["Tell me about my project", "Which layer groups are there?", "What is on the map now?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the project as a whole.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        project = QgsProject.instance()
        title = self._safe(project.title)
        file_path = self._safe(project.fileName)
        file_name = os.path.basename(file_path or "")
        return {
            "title": title,
            "display_name": title or self._name_from_path(file_path) or "unnamed",
            "file_name": file_name,
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
                f"$length and $area are measured on ellipsoid {ellipsoid} and returned "
                "in project units, even when the layer is stored in degrees."
            )
        return (
            "No ellipsoid is set: $length and $area are returned in the units of the layer CRS. "
            "For a layer in degrees such values are meaningless."
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
