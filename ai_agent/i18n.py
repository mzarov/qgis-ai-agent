import os
from contextlib import suppress
from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QTranslator

CONTEXT = "QgisAiAgent"
FOLDER = "translations"
PREFIX = "ai_agent"
SUFFIX = ".qm"
FALLBACK_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "ru")
_TRANSLATOR: list[Any] = []


def tr(text: str) -> str:
    return _translate(text)


def _translate(text: str) -> str:
    try:
        translated = QCoreApplication.translate(CONTEXT, text)
    except Exception:
        return text
    return translated if isinstance(translated, str) and translated else text


def tr_data(text: str) -> str:
    """Translate a text that comes from a data file, not a literal in code.

    The connector JSON texts reach the catalogue through
    tools/update_translations.py, which reads those files; tr() itself takes
    literals only, so the extractor can find every string in the sources.
    """
    return _translate(text)


def tr_n(text: str, count: int) -> str:
    try:
        translated = QCoreApplication.translate(CONTEXT, text, None, count)
    except Exception:
        translated = ""
    if not isinstance(translated, str) or not translated:
        translated = text
    # Without a catalogue Qt hands the source back with %n already filled in.
    if translated in (text, text.replace("%n", str(count))) and "(s)" in translated:
        translated = translated.replace("(s)", "" if count == 1 else "s")
    return translated.replace("%n", str(count))


def locale_code() -> str:
    from qgis.core import QgsSettings

    try:
        stored = QgsSettings().value("locale/userLocale", "", type=str)
    except Exception:
        stored = ""
    if not isinstance(stored, str) or not stored.strip():
        return FALLBACK_LOCALE
    language = stored.strip().split("_")[0].lower()
    return language if language in SUPPORTED_LOCALES else FALLBACK_LOCALE


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
        with suppress(Exception):
            QCoreApplication.removeTranslator(_TRANSLATOR.pop())
