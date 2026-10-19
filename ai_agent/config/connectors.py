from collections.abc import Iterable

from qgis.core import QgsSettings

SETTINGS_PREFIX = "ai_agent"
KEY = "connectors/disabled"
SEPARATOR = ","


def disabled_connectors() -> frozenset[str]:
    raw = QgsSettings().value(f"{SETTINGS_PREFIX}/{KEY}", "", type=str)
    text = raw if isinstance(raw, str) else ""
    return frozenset(item.strip() for item in text.split(SEPARATOR) if item.strip())


def set_disabled_connectors(identifiers: Iterable[str]) -> None:
    settings = QgsSettings()
    settings.setValue(
        f"{SETTINGS_PREFIX}/{KEY}", SEPARATOR.join(sorted({item.strip() for item in identifiers if item}))
    )
    settings.sync()
