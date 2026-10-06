"""What the other installed plugins offer: metadata, their Processing algorithms, their menu commands.

A plugin is known by its package folder name, the key QGIS itself uses
(qgis.utils.active_plugins). Processing providers belong to a plugin when their
class lives in its package; menu commands are the actions under the submenu a
plugin adds to Plugins, Vector, Raster, Database, Web or Mesh.
"""

from typing import Any

from qgis.core import QgsApplication

# This plugin's own package; it is never offered as something to drive.
SELF = __name__.split(".")[0]
MISSING = "__error__"
PATH_SEPARATOR = " › "
ABOUT_CHARS = 600
# A menu title must cover this much of a plugin name to count as the plugin's own menu.
NAME_SHARE = 0.6


def qgis_utils() -> Any:
    import qgis.utils

    return qgis.utils


def active_plugins() -> list[str]:
    try:
        names = list(qgis_utils().active_plugins)
    except Exception:
        return []
    return sorted(name for name in names if name != SELF)


def metadata(plugin: str, key: str) -> str:
    try:
        value = str(qgis_utils().pluginMetadata(plugin, key) or "")
    except Exception:
        return ""
    return "" if value == MISSING else " ".join(value.split())


def require_plugin(name: Any) -> str:
    """The package name of an active plugin, matched by package or display name; else a ValueError with the list."""
    wanted = str(name or "").strip()
    active = active_plugins()
    for plugin in active:
        if wanted.lower() in (plugin.lower(), metadata(plugin, "name").lower()):
            return plugin
    shown = ", ".join(active) or "none"
    raise ValueError(f"No active plugin '{wanted}'. Active plugins: {shown}. See list_plugins.")


def providers(plugin: str) -> list[Any]:
    try:
        registered = list(QgsApplication.processingRegistry().providers())
    except Exception:
        return []
    return [provider for provider in registered if type(provider).__module__.split(".")[0] == plugin]


def algorithms(provider: Any) -> list[dict[str, str]]:
    try:
        return [{"id": item.id(), "name": item.displayName()} for item in provider.algorithms()]
    except Exception:
        return []


def menu_commands(plugin: str) -> dict[str, Any]:
    """Command path → QAction for every leaf under the plugin's own menus: a submenu of a top menu, or a top menu."""
    names = {_key(plugin), _key(metadata(plugin, "name"))} - {""}
    found: dict[str, Any] = {}
    for top in _menu_bar_actions():
        menu = top.menu()
        if menu is None:
            continue
        if _matches(top.text(), names):
            _collect(menu, [_clean(top.text())], found)
            continue
        for entry in menu.actions():
            submenu = entry.menu()
            if submenu is not None and _matches(entry.text(), names):
                _collect(submenu, [_clean(top.text()), _clean(entry.text())], found)
    return found


def _matches(title: Any, names: set[str]) -> bool:
    """A menu titled after the plugin: the same letters, or most of its name.

    QuickMapServices files its menu as "QuickMapServices" while its name is "NextGIS
    QuickMapServices"; "Processing" is only a fragment of "GRASS Processing Provider".
    """
    key = _key(_clean(title))
    return bool(key) and any(key == name or (key in name and len(key) >= NAME_SHARE * len(name)) for name in names)


def _key(text: Any) -> str:
    return "".join(char for char in str(text or "").lower() if char.isalnum())


def _menu_bar_actions() -> list[Any]:
    try:
        return list(qgis_utils().iface.mainWindow().menuBar().actions())
    except Exception:
        return []


def _collect(menu: Any, trail: list[str], found: dict[str, Any]) -> None:
    for action in menu.actions():
        if action.isSeparator():
            continue
        text = _clean(action.text())
        if action.menu() is not None:
            _collect(action.menu(), [*trail, text], found)
        elif text:
            found[PATH_SEPARATOR.join([*trail, text])] = action


def _clean(text: Any) -> str:
    """Menu text without the & mnemonic marker or a trailing ellipsis."""
    return (
        " ".join(str(text or "").replace("&&", "\0").replace("&", "").replace("\0", "&").split()).rstrip(".…").strip()
    )
