import os
import tempfile
import time

from qgis.core import Qgis, QgsMessageLog, QgsProject

LOG_TAG = "AI Agent"
FOLDER = "ai_agent_snapshots"
PREFIX = "before_apply"
SUFFIX = ".qgz"
MAX_SNAPSHOTS = 10
_LAST: list[str] = []


def snapshot_folder() -> str:
    folder = os.path.join(tempfile.gettempdir(), FOLDER)
    os.makedirs(folder, exist_ok=True)
    return folder


def take_snapshot() -> str:
    try:
        return _write_snapshot()
    except Exception as failure:
        QgsMessageLog.logMessage(f"Could not snapshot the project: {failure}", LOG_TAG, Qgis.Warning)
        return ""


def _write_snapshot() -> str:
    path = os.path.join(snapshot_folder(), f"{PREFIX}_{int(time.time() * 1000)}{SUFFIX}")
    if not QgsProject.instance().write(path):
        return ""
    _LAST.append(path)
    _trim()
    QgsMessageLog.logMessage(f"Project snapshot written: {path}", LOG_TAG, Qgis.Info)
    return path


def last_snapshot() -> str:
    while _LAST:
        candidate = _LAST[-1]
        if os.path.isfile(candidate):
            return candidate
        _LAST.pop()
    return ""


def drop_last() -> None:
    if _LAST:
        _LAST.pop()


def _trim() -> None:
    while len(_LAST) > MAX_SNAPSHOTS:
        stale = _LAST.pop(0)
        try:
            os.remove(stale)
        except OSError:
            continue
