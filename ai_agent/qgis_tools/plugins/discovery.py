from typing import Any

from qgis.core import QgsApplication

SELF = __name__.split(".")[0]
MISSING = "__error__"
PATH_SEPARATOR = " › "
ABOUT_CHARS = 600
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
    return (
        " ".join(str(text or "").replace("&&", "\0").replace("&", "").replace("\0", "&").split()).rstrip(".…").strip()
    )
