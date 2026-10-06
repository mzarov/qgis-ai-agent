from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.project.restore import restore_snapshot
from ai_agent.qgis_tools.project.snapshots import last_snapshot, snapshot_scratch

NOTHING_TO_UNDO = (
    "There is no snapshot to go back to: nothing has been applied in this "
    "QGIS session yet, or the snapshot file is gone."
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
    egress = EGRESS_METADATA
    external_effect = False
    network_access = False
    constraints = ["A plan must have been applied in this session"]
    examples = ["Undo that", "Roll back the last change"]
    params_schema = []

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        path = last_snapshot()
        if not path:
            raise ValueError(NOTHING_TO_UNDO)
        return {**params, "_snapshot_path": path}

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Rolling the project back to before the last applied plan.")

    def detail_call(self, params: dict[str, Any]) -> str:
        path = str(params.get("_snapshot_path") or last_snapshot())
        lost = snapshot_scratch(path).not_copied if path else ()
        if not lost:
            return ""
        return tr("These temporary layers will come back empty: {0}.").format(", ".join(lost))

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        path = str(params.get("_snapshot_path") or last_snapshot())
        if not path:
            raise ValueError(NOTHING_TO_UNDO)
        return restore_snapshot(path)
