from typing import Any

from qgis.core import QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.project.snapshots import drop_last, last_snapshot

NOTHING_TO_UNDO = (
    "There is no snapshot to go back to: nothing has been applied in this "
    "QGIS session yet, or the snapshot file is gone."
)
SCOPE_NOTE = (
    "This restores the project file — layers, styling, layout. Edits written "
    "into a data source (attribute changes, deleted features) are NOT undone."
)


class UndoLastApplyTool(BaseTool):
    name = "undo_last_apply"
    description = (
        "Roll the project back to the snapshot taken before the last applied "
        "plan. Restores layers, styling and layouts; it cannot undo edits that "
        "were written into a data source."
    )
    skill = "project"
    safety = SAFETY_DESTRUCTIVE
    constraints = ["A plan must have been applied in this session"]
    examples = ["Undo that", "Roll back the last change"]
    params_schema = []

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        if not last_snapshot():
            raise ValueError(NOTHING_TO_UNDO)
        return dict(params)

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Rolling the project back to before the last applied plan.")

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        path = last_snapshot()
        if not path:
            raise ValueError(NOTHING_TO_UNDO)
        if not QgsProject.instance().read(path):
            raise ValueError(f"QGIS could not read the snapshot at {path}.")
        drop_last()
        return {"restored_from": path, "note": SCOPE_NOTE}
