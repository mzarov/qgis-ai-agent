from typing import Any

from qgis.core import QgsProject

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_METADATA, SAFETY_DESTRUCTIVE, BaseTool
from ai_agent.qgis_tools.project.scratch_copies import restore_scratch_layers
from ai_agent.qgis_tools.project.snapshots import (
    capture_project_state,
    drop_snapshot,
    ensure_project_read_safe,
    last_snapshot,
    restore_project_state,
    snapshot_scratch,
    snapshot_state,
)

NOTHING_TO_UNDO = (
    "There is no snapshot to go back to: nothing has been applied in this "
    "QGIS session yet, or the snapshot file is gone."
)
SCOPE_NOTE = (
    "This restores the project file — layers, styling, layout. Edits written "
    "into a data source (attribute changes, deleted features) are NOT undone."
)
EMPTY_SCRATCH_NOTE = (
    "These temporary (memory) layers came back without their features: {layers}. They were too "
    "large to copy beside the snapshot or could not be refilled. Re-run the steps that produced "
    "them, and export scratch layers with export_layer when they must survive an undo."
)
OTHER_PROJECT = (
    "The newest snapshot belongs to another project ('{expected}'), while "
    "the current project is '{current}'. Switch back before undoing it."
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
        project = QgsProject.instance()
        ensure_project_read_safe(project)
        before_read = capture_project_state(project)
        original = snapshot_state(path)
        if original is not None and before_read.identity != original.identity:
            raise ValueError(
                OTHER_PROJECT.format(
                    expected=original.file_name or "unsaved project",
                    current=before_read.file_name or "unsaved project",
                )
            )
        try:
            restored = bool(project.read(path))
        except Exception as failure:
            restore_project_state(project, before_read)
            raise ValueError(f"QGIS could not read the snapshot at {path}: {failure}.") from None
        if not restored:
            restore_project_state(project, before_read)
            raise ValueError(f"QGIS could not read the snapshot at {path}.")
        restore_project_state(project, original or before_read, mark_dirty=True)
        scratch = snapshot_scratch(path)
        empty = [*scratch.not_copied, *restore_scratch_layers(project, scratch)]
        drop_snapshot(path)
        result: dict[str, Any] = {"restored_from": path, "note": SCOPE_NOTE}
        if empty:
            result["empty_scratch_layers"] = empty
            result["scratch_note"] = EMPTY_SCRATCH_NOTE.format(layers=", ".join(empty))
        return result
