import atexit
import os
import tempfile
import time
import zipfile
from dataclasses import dataclass, replace

from qgis.core import Qgis, QgsMessageLog, QgsProject

from ai_agent.qgis_tools.common.project_identity import project_identity, restore_project_identity
from ai_agent.qgis_tools.project.scratch_copies import ScratchCopies, copy_scratch_layers

LOG_TAG = "AI Agent"
FOLDER = "ai_agent_snapshots"
PREFIX = "before_apply"
SUFFIX = ".qgz"
MAX_SNAPSHOTS = 10
MAX_WRITE_ATTEMPTS = 3
_LAST: list[str] = []
_STATES: dict[str, "ProjectState"] = {}
_SCRATCH: dict[str, ScratchCopies] = {}
_LAST_ERROR = ""
_PROCESS_FOLDER = ""
EDIT_BUFFER_ERROR = (
    "QGIS has an active edit buffer on: {layers}. Commit or roll back those manual edits first; "
    "a project snapshot cannot preserve them safely."
)


@dataclass(frozen=True)
class ProjectState:
    file_name: str = ""
    preset_home_path: str = ""
    dirty: bool = False
    identity: str = ""


def snapshot_folder() -> str:
    global _PROCESS_FOLDER
    if not _PROCESS_FOLDER:
        _PROCESS_FOLDER = tempfile.mkdtemp(prefix=FOLDER + "_")
    try:
        os.chmod(_PROCESS_FOLDER, 0o700)
    except OSError:
        pass
    return _PROCESS_FOLDER


def take_snapshot() -> str:
    global _LAST_ERROR
    _LAST_ERROR = ""
    try:
        return _write_snapshot()
    except Exception as failure:
        _LAST_ERROR = str(failure).strip() or type(failure).__name__
        QgsMessageLog.logMessage(f"Could not snapshot the project: {failure}", LOG_TAG, Qgis.MessageLevel.Warning)
        return ""


def snapshot_error() -> str:
    return _LAST_ERROR


def _write_snapshot() -> str:
    path = os.path.join(snapshot_folder(), f"{PREFIX}_{time.time_ns()}{SUFFIX}")
    project = QgsProject.instance()
    ensure_project_read_safe(project)
    state = capture_project_state(project)
    try:
        written = _write_own_archive(project, path)
    except Exception:
        _remove_file(path)
        raise
    finally:
        restore_project_state(project, state)
    if not written:
        _remove_file(path)
        return ""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _LAST.append(path)
    _STATES[path] = state
    _SCRATCH[path] = copy_scratch_layers(project)
    _trim()
    QgsMessageLog.logMessage(f"Project snapshot written: {path}", LOG_TAG, Qgis.MessageLevel.Info)
    return path


def _write_own_archive(project: QgsProject, path: str) -> bool:
    # QGIS zips every .qgz through one fixed file in the system temp folder, shared by all its processes.
    for _ in range(MAX_WRITE_ATTEMPTS):
        if project.write(path) and _holds_own_project(path):
            return True
        QgsMessageLog.logMessage(
            f"The project snapshot failed or another QGIS overwrote it ({_project_error(project)}).",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )
        _remove_file(path)
    return False


def _holds_own_project(path: str) -> bool:
    expected = os.path.basename(path).split(".", 1)[0] + ".qgs"
    try:
        with zipfile.ZipFile(path) as archive:
            return expected in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _project_error(project: QgsProject) -> str:
    try:
        return str(project.error()).strip() or "QGIS gave no reason"
    except Exception:
        return "QGIS gave no reason"


def last_snapshot() -> str:
    while _LAST:
        candidate = _LAST[-1]
        if os.path.isfile(candidate):
            return candidate
        _LAST.pop()
        _STATES.pop(candidate, None)
        _SCRATCH.pop(candidate, None)
    return ""


def snapshot_exists(path: str) -> bool:
    return path in _LAST and os.path.isfile(path)


def drop_snapshot(path: str) -> None:
    try:
        _LAST.remove(path)
    except ValueError:
        pass
    _STATES.pop(path, None)
    _SCRATCH.pop(path, None)
    _remove_file(path)


def snapshot_state(path: str) -> ProjectState | None:
    return _STATES.get(path)


def follow_project_move(identity: str) -> None:
    current = capture_project_state(QgsProject.instance())
    for path, state in list(_STATES.items()):
        if state.identity == identity:
            _STATES[path] = replace(
                state,
                file_name=current.file_name,
                preset_home_path=current.preset_home_path,
                identity=current.identity,
            )


def snapshot_scratch(path: str) -> ScratchCopies:
    return _SCRATCH.get(path) or ScratchCopies()


def capture_project_state(project: QgsProject) -> ProjectState:
    return ProjectState(
        file_name=_string_property(project, "fileName"),
        preset_home_path=_string_property(project, "presetHomePath"),
        dirty=_bool_property(project, "isDirty"),
        identity=project_identity(project),
    )


def ensure_project_read_safe(project: QgsProject) -> None:
    active = []
    try:
        layers = project.mapLayers().values()
    except Exception:
        layers = []
    for layer in layers:
        try:
            editing = bool(layer.isEditable())
        except Exception:
            editing = False
        if editing:
            try:
                name = (layer.name() or "Unnamed").strip()
            except Exception:
                name = "Unnamed"
            active.append(name)
    if active:
        raise ValueError(EDIT_BUFFER_ERROR.format(layers=", ".join(sorted(active))))


def restore_project_state(project: QgsProject, state: ProjectState, *, mark_dirty: bool | None = None) -> None:
    project.setFileName(state.file_name)
    try:
        project.setPresetHomePath(state.preset_home_path)
    except (AttributeError, TypeError):
        pass
    project.setDirty(state.dirty if mark_dirty is None else mark_dirty)
    restore_project_identity(project, state.identity)


def _trim() -> None:
    while len(_LAST) > MAX_SNAPSHOTS:
        stale = _LAST.pop(0)
        _STATES.pop(stale, None)
        _SCRATCH.pop(stale, None)
        _remove_file(stale)


def _string_property(project: QgsProject, name: str) -> str:
    try:
        value = getattr(project, name)()
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _bool_property(project: QgsProject, name: str) -> bool:
    try:
        return bool(getattr(project, name)())
    except Exception:
        return False


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _cleanup_process_folder() -> None:
    folder = _PROCESS_FOLDER
    if not folder:
        return
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        path = os.path.join(folder, name)
        if name.startswith(PREFIX + "_") and name.endswith(SUFFIX):
            _remove_file(path)
    try:
        os.rmdir(folder)
    except OSError:
        pass


atexit.register(_cleanup_process_folder)
