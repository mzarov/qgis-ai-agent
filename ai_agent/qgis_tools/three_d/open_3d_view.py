from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_WRITE, BaseTool

DEFAULT_NAME = "3D Map"
NOT_SUPPORTED = (
    "This QGIS build cannot open a 3D view from code — the API is missing. "
    "Ask the user to open one through View → 3D Map Views; run_python can "
    "then adjust it."
)


class Open3dViewTool(BaseTool):
    name = "open_3d_view"
    description = (
        "Open a new 3D map view showing the current layers. Terrain, camera "
        "and exaggeration are then adjusted through run_python — this tool "
        "only opens the window."
    )
    skill = "three_d"
    safety = SAFETY_WRITE
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["Needs a QGIS build with 3D support"]
    examples = ["Show this in 3D", "Open a 3D view"]
    params_schema = [
        {"name": "name", "type": "string", "description": f"View name, default '{DEFAULT_NAME}'", "required": False},
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Opening a 3D view '{0}'.").format(str(params.get("name") or DEFAULT_NAME).strip() or DEFAULT_NAME)

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or DEFAULT_NAME).strip() or DEFAULT_NAME
        opener = _find_opener()
        if opener is None:
            raise ValueError(NOT_SUPPORTED)
        try:
            opener(name)
        except TypeError:
            opener()
        return {"view": name, "note": "Terrain and camera are adjusted through run_python."}


def _find_opener() -> Any:
    try:
        from qgis.utils import iface
    except Exception:
        return None
    for attribute in ("createNewMapCanvas3D", "createNew3DMapCanvas", "createNewMapCanvas3d"):
        opener = getattr(iface, attribute, None)
        if callable(opener):
            return opener
    return None
