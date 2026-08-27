import os
from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QTranslator

CONTEXT = "QgisAiAgent"
FOLDER = "i18n"
PREFIX = "qgis_ai_agent"
SUFFIX = ".qm"
FALLBACK_LOCALE = "en"
_TRANSLATOR: list[Any] = []


def tr(text: str) -> str:
    try:
        translated = QCoreApplication.translate(CONTEXT, text)
    except Exception:
        return text
    return translated if isinstance(translated, str) and translated else text


def tr_n(text: str, count: int) -> str:
    try:
        translated = QCoreApplication.translate(CONTEXT, text, None, count)
    except Exception:
        translated = ""
    if not isinstance(translated, str) or not translated:
        translated = text
    return translated.replace("%n", str(count))


def locale_code() -> str:
    from qgis.core import QgsSettings

    try:
        stored = QgsSettings().value("locale/userLocale", "", type=str)
    except Exception:
        stored = ""
    if not isinstance(stored, str) or not stored.strip():
        return FALLBACK_LOCALE
    return stored.strip().split("_")[0].lower()


def install(plugin_dir: str) -> bool:
    try:
        return _install(plugin_dir)
    except Exception:
        return False


def _install(plugin_dir: str) -> bool:
    language = locale_code()
    path = os.path.join(plugin_dir, FOLDER, f"{PREFIX}_{language}{SUFFIX}")
    if language == FALLBACK_LOCALE or not os.path.isfile(path):
        return False
    translator = QTranslator()
    if not translator.load(path):
        return False
    if not QCoreApplication.installTranslator(translator):
        return False
    _TRANSLATOR.append(translator)
    return True


def remove() -> None:
    while _TRANSLATOR:
        try:
            QCoreApplication.removeTranslator(_TRANSLATOR.pop())
        except Exception:
            continue
