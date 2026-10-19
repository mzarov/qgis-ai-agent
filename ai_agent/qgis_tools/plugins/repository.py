import io
import os
import time
import zipfile
from contextlib import suppress
from pathlib import PurePosixPath
from typing import Any

from qgis.core import Qgis, QgsApplication, QgsSettings
from qgis.PyQt.QtXml import QDomDocument

from ai_agent.qgis_tools.plugins.discovery import active_plugins, qgis_utils

REPOSITORY_URL = "https://plugins.qgis.org/plugins/plugins.xml?qgis={version}"
MAX_LIST_BYTES = 32 * 1024 * 1024
MAX_ZIP_BYTES = 200 * 1024 * 1024
CACHE_SECONDS = 3600
ENABLED_SETTING = "PythonPlugins/{0}"
TRUE_TEXTS = ("true", "1", "yes")
_CACHE: dict[str, Any] = {"entries": None, "fetched": 0.0}


def repository_url() -> str:
    parts = str(Qgis.version()).split(".")
    return REPOSITORY_URL.format(version=".".join(parts[:2]))


def cached_entries() -> list[dict[str, Any]] | None:
    entries = _CACHE["entries"]
    if entries is None or time.monotonic() - float(_CACHE["fetched"]) > CACHE_SECONDS:
        return None
    return list(entries)


def remember(entries: list[dict[str, Any]]) -> None:
    _CACHE["entries"], _CACHE["fetched"] = list(entries), time.monotonic()


def parse_repository(xml: bytes) -> list[dict[str, Any]]:
    document = QDomDocument()
    parsed = document.setContent(bytes(xml))
    if not (parsed[0] if isinstance(parsed, tuple) else parsed):
        raise ValueError("plugins.qgis.org sent a plugin list that is not valid XML. Try again later.")
    nodes = document.elementsByTagName("pyqgis_plugin")
    entries = []
    for index in range(nodes.count()):
        element = nodes.item(index).toElement()
        version = element.attribute("version")
        entry = {
            "key": plugin_key(_text(element, "file_name"), version),
            "name": element.attribute("name"),
            "version": version,
            "description": _text(element, "description"),
            "about": _text(element, "about"),
            "tags": [tag.strip() for tag in _text(element, "tags").split(",") if tag.strip()],
            "author": _text(element, "author_name"),
            "downloads": _number(_text(element, "downloads")),
            "experimental": _text(element, "experimental").lower() in TRUE_TEXTS,
            "deprecated": _text(element, "deprecated").lower() in TRUE_TEXTS,
            "download_url": _text(element, "download_url"),
        }
        if entry["key"] and entry["download_url"]:
            entries.append(entry)
    return entries


def plugin_key(file_name: str, version: str) -> str:
    name = str(file_name or "").strip()
    suffix = f".{version}.zip"
    if version and name.endswith(suffix):
        return name[: -len(suffix)]
    return name.split(".")[0]


def installed_plugins() -> set[str]:
    try:
        return set(qgis_utils().available_plugins)
    except Exception:
        return set()


def find_entry(entries: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    text = str(wanted or "").strip().lower()
    for entry in entries:
        if text in (entry["key"].lower(), entry["name"].lower()):
            return entry
    return None


def unpacked(archive: bytes, plugins_folder: str) -> str:
    # Zip-slip guard: one top folder, no absolute path or `..`; an existing folder is never overwritten.
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile:
        raise ValueError("The plugin download is not a zip archive; nothing was installed.") from None
    names = bundle.namelist()
    tops = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
    unsafe = [name for name in names if name.startswith("/") or ".." in PurePosixPath(name).parts or "\\" in name]
    if unsafe or len(tops) != 1:
        raise ValueError("The plugin archive does not hold one plugin folder; nothing was installed.")
    key = tops.pop()
    target = os.path.join(plugins_folder, key)
    if os.path.exists(target):
        raise ValueError(f"A plugin folder '{key}' already exists; update it in Plugins → Manage and Install Plugins.")
    os.makedirs(plugins_folder, exist_ok=True)
    bundle.extractall(plugins_folder)
    return key


def plugins_folder() -> str:
    folder = getattr(qgis_utils(), "home_plugin_path", "")
    return str(folder or os.path.join(QgsApplication.qgisSettingsDirPath(), "python", "plugins"))


def enable(key: str) -> None:
    utils = qgis_utils()
    with suppress(Exception):
        utils.updateAvailablePlugins()
    if key not in active_plugins():
        if not utils.loadPlugin(key):
            raise ValueError(f"QGIS could not load the plugin '{key}'. See the Plugins tab of the message log.")
        if not utils.startPlugin(key):
            raise ValueError(f"QGIS could not start the plugin '{key}'. See the Plugins tab of the message log.")
    QgsSettings().setValue(ENABLED_SETTING.format(key), True)
    with suppress(Exception):
        import pyplugin_installer

        pyplugin_installer.instance().reloadAndExportData()


def _text(element: Any, tag: str) -> str:
    return " ".join(str(element.firstChildElement(tag).text() or "").split())


def _number(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0
