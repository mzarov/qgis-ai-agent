from typing import Any

from qgis.core import QgsProject

from ai_agent.qgis_tools.common.project_identity import same_project
from ai_agent.qgis_tools.project.scratch_copies import restore_scratch_layers
from ai_agent.qgis_tools.project.snapshots import (
    capture_project_state,
    drop_snapshot,
    ensure_project_read_safe,
    restore_project_state,
    snapshot_scratch,
    snapshot_state,
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
RENUMBERED_NOTE = (
    "These temporary (memory) layers came back with new feature ids: {layers}. Too many ids were missing "
    "between their features to keep each one's own; a virtual field or anything else built on $id may now "
    "read differently."
)
SAVED_AS_NOTE = (
    "The undone steps saved the project as '{saved}'; that file still holds them. The project is back "
    "where it was before them: {original}."
)
OTHER_PROJECT = (
    "The snapshot belongs to another project ('{expected}'), while "
    "the current project is '{current}'. Switch back before restoring it."
)


def restore_snapshot(path: str) -> dict[str, Any]:
    project = QgsProject.instance()
    ensure_project_read_safe(project)
    before_read = capture_project_state(project)
    original = snapshot_state(path)
    if original is not None and not same_project(before_read.identity, original.identity):
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
    if original is not None and before_read.identity != original.identity:
        result["saved_as_note"] = SAVED_AS_NOTE.format(
            saved=before_read.file_name, original=original.file_name or "an unsaved project"
        )
    if empty:
        result["empty_scratch_layers"] = empty
        result["scratch_note"] = EMPTY_SCRATCH_NOTE.format(layers=", ".join(empty))
    renumbered = [copy.name for copy in scratch.layers if not copy.keeps_ids and copy.name not in empty]
    if renumbered:
        result["renumbered_scratch_layers"] = renumbered
        result["renumbered_note"] = RENUMBERED_NOTE.format(layers=", ".join(renumbered))
    return result
