"""Where downloaded files land: next to a saved project, or in a private temporary folder."""

import os
import tempfile

from qgis.core import QgsProject

PROJECT_FOLDER = "open_data"
FOLDER_PREFIX = "ai-agent-data-"
MAX_ATTEMPTS = 1000
TEMP_NOTE = (
    "The project is not saved, so the file sits in a temporary folder the system may clear. "
    "Save the project into a folder, or export the layer with export_layer, to keep it."
)


def target_path(stem: str, suffix: str) -> tuple[str, bool]:
    """A free file path for the download and whether it is temporary."""
    home = _project_home()
    if home:
        folder = os.path.join(home, PROJECT_FOLDER)
        os.makedirs(folder, exist_ok=True)
        temporary = False
    else:
        folder = tempfile.mkdtemp(prefix=FOLDER_PREFIX)
        os.chmod(folder, 0o700)
        temporary = True
    slug = "".join(char if char.isalnum() or char in "-_" else "_" for char in stem)[:60] or "data"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        path = os.path.join(folder, (slug if attempt == 1 else f"{slug}_{attempt}") + suffix)
        if not os.path.exists(path):
            return path, temporary
    raise ValueError(f"{folder} already holds too many files named '{slug}'. Pick another name.")


def _project_home() -> str:
    try:
        home = QgsProject.instance().homePath()
    except Exception:
        return ""
    return home if isinstance(home, str) and home.strip() and os.path.isdir(home) else ""
