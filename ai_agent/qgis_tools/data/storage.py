import os

from ai_agent.qgis_tools.common.paths import download_folder, file_slug

PROJECT_FOLDER = "open_data"
FOLDER_PREFIX = "ai-agent-data-"
MAX_ATTEMPTS = 1000
FALLBACK_STEM = "data"
TEMP_NOTE = (
    "The project is not saved, so the file sits in a temporary folder the system may clear. "
    "Save the project into a folder, or export the layer with export_layer, to keep it."
)


def target_path(stem: str, suffix: str) -> tuple[str, bool]:
    folder, temporary = download_folder(PROJECT_FOLDER, FOLDER_PREFIX)
    slug = file_slug(stem, FALLBACK_STEM)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        path = os.path.join(folder, (slug if attempt == 1 else f"{slug}_{attempt}") + suffix)
        if not os.path.exists(path):
            return path, temporary
    raise ValueError(f"{folder} already holds too many files named '{slug}'. Pick another name.")
