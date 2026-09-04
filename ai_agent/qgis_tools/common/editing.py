from collections.abc import Iterator
from contextlib import contextmanager

from qgis.core import QgsVectorLayer

PARTIAL_COMMIT_NOTE = "The data source may already contain partial changes; inspect it before retrying."


@contextmanager
def edit_session(layer: QgsVectorLayer, operation: str) -> Iterator[None]:
    if layer.isEditable():
        raise ValueError(
            f"Layer '{layer.name()}' already has an active edit session. "
            "Commit or roll back those edits before applying this change."
        )
    if not layer.startEditing():
        raise ValueError(
            f"Layer '{layer.name()}' cannot be switched into editing mode. "
            "Its data source is read-only or does not support editing; use an editable copy."
        )
    commit_attempted = False
    try:
        yield
        commit_attempted = True
        if not layer.commitChanges():
            reason = "; ".join(layer.commitErrors() or []) or "provider refused"
            raise ValueError(f"QGIS could not commit {operation}: {reason}.")
    except Exception as failure:
        message = str(failure).strip() or type(failure).__name__
        recovery = _rollback_note(layer)
        if commit_attempted:
            recovery = f"{recovery} {PARTIAL_COMMIT_NOTE}"
        raise ValueError(f"{message} {recovery}") from failure


def _rollback_note(layer: QgsVectorLayer) -> str:
    try:
        if layer.rollBack():
            return "Uncommitted edits were discarded."
    except Exception as failure:
        reason = str(failure).strip() or type(failure).__name__
        return f"Rollback failed: {reason}. Inspect the layer's edit session before continuing."
    return "QGIS could not roll back the edit session. Inspect the layer before continuing."
