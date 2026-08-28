from typing import Any

from qgis.core import QgsApplication, QgsBookmark, QgsProject, QgsReferencedRectangle

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.qgis_tools.base import SAFETY_READ, SAFETY_WRITE, BaseTool
from qgis_ai_agent.qgis_tools.common.layers import canvas_extent, extent_dict
from qgis_ai_agent.qgis_tools.project.tree import project

NO_THEMES_NOTE = (
    "The project has no map themes. A theme remembers which layers are "
    "visible and how they are styled — save one with save_map_theme."
)


def bookmark_manager() -> Any:
    return QgsApplication.bookmarkManager()


def project_themes() -> list[str]:
    try:
        return list(project().mapThemeCollection().mapThemes())
    except Exception:
        return []


class ListViewsTool(BaseTool):
    name = "list_views"
    description = (
        "List the saved spatial bookmarks and the map themes of the project — "
        "the named places and the named layer-visibility presets."
    )
    skill = "project"
    safety = SAFETY_READ
    examples = ["Which bookmarks do I have?", "What map themes are saved?"]
    params_schema = []

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading the saved bookmarks and map themes.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        bookmarks = sorted(_bookmark_names())
        themes = sorted(project_themes())
        result: dict[str, Any] = {"bookmarks": bookmarks, "map_themes": themes}
        if not themes:
            result["themes_note"] = NO_THEMES_NOTE
        return result


class SaveBookmarkTool(BaseTool):
    name = "save_bookmark"
    description = "Save the current map view as a named spatial bookmark, so it can be returned to later."
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["The bookmark name must be new"]
    examples = ["Remember this view as 'city centre'"]
    params_schema = [
        {"name": "name", "type": "string", "description": "Bookmark name", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        if not name:
            raise ValueError("The bookmark needs a name.")
        if name in _bookmark_names():
            raise ValueError(f"A bookmark named '{name}' already exists. Pick another name.")
        prepared = dict(params)
        prepared["name"] = name
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Saving the current view as bookmark '{0}'.").format(str(params.get("name") or ""))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        extent = canvas_extent()
        bookmark = QgsBookmark()
        bookmark.setName(name)
        bookmark.setExtent(QgsReferencedRectangle(extent, QgsProject.instance().crs()))
        bookmark_manager().addBookmark(bookmark)
        return {"bookmark": name, "extent": extent_dict(extent)}


class SaveMapThemeTool(BaseTool):
    name = "save_map_theme"
    description = (
        "Save the current layer visibility and styling as a named map theme, "
        "so the whole look can be switched back on later."
    )
    skill = "project"
    safety = SAFETY_WRITE
    constraints = ["The theme name must be new"]
    examples = ["Save this look as 'print version'"]
    params_schema = [
        {"name": "name", "type": "string", "description": "Map theme name", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        if not name:
            raise ValueError("The map theme needs a name.")
        if name in project_themes():
            raise ValueError(f"A map theme named '{name}' already exists. Pick another name.")
        prepared = dict(params)
        prepared["name"] = name
        return prepared

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Saving the current look as map theme '{0}'.").format(str(params.get("name") or ""))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        from qgis.core import QgsMapThemeCollection

        name = str(params.get("name") or "").strip()
        instance = project()
        root = instance.layerTreeRoot()
        model = _layer_tree_model(root)
        record = QgsMapThemeCollection.createThemeFromCurrentState(root, model)
        instance.mapThemeCollection().insert(name, record)
        return {"map_theme": name, "themes": sorted(project_themes())}


def _bookmark_names() -> list[str]:
    try:
        return [bookmark.name() for bookmark in bookmark_manager().bookmarks()]
    except Exception:
        return []


def _layer_tree_model(root: Any) -> Any:
    try:
        from qgis.utils import iface

        return iface.layerTreeView().layerTreeModel()
    except Exception:
        from qgis.core import QgsLayerTreeModel

        return QgsLayerTreeModel(root)
