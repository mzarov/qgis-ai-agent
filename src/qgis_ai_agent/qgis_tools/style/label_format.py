from typing import Any

from qgis.core import QgsTextBufferSettings, QgsTextFormat

from qgis_ai_agent.qgis_tools.style.apply import parse_color

DEFAULT_SIZE = 9.0
MIN_SIZE = 3.0
MAX_SIZE = 72.0
DEFAULT_BUFFER_SIZE = 1.0
MIN_BUFFER_SIZE = 0.1
MAX_BUFFER_SIZE = 10.0
DEFAULT_BUFFER_COLOR = "white"
FALSE_WORDS = ("false", "0", "no", "off")


def text_format(params: dict[str, Any]) -> QgsTextFormat:
    text_format = QgsTextFormat()
    text_format.setSize(font_size(params.get("size")))
    if params.get("color"):
        text_format.setColor(parse_color(params.get("color"), "Цвет подписи"))
    text_format.setBuffer(buffer_settings(params))
    return text_format


def buffer_settings(params: dict[str, Any]) -> QgsTextBufferSettings:
    buffer = QgsTextBufferSettings()
    if not wants_buffer(params):
        buffer.setEnabled(False)
        return buffer
    buffer.setEnabled(True)
    buffer.setSize(buffer_size(params.get("buffer_size")))
    buffer.setColor(parse_color(params.get("buffer_color") or DEFAULT_BUFFER_COLOR, "Цвет обводки текста"))
    return buffer


def wants_buffer(params: dict[str, Any]) -> bool:
    asked = params.get("buffer")
    if asked is not None:
        if isinstance(asked, str):
            return asked.strip().lower() not in FALSE_WORDS
        return bool(asked)
    return bool(params.get("buffer_color") or params.get("buffer_size") is not None)


def buffer_size(value: Any) -> float:
    if value is None:
        return DEFAULT_BUFFER_SIZE
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Толщина обводки текста задаётся числом от {MIN_BUFFER_SIZE:g} "
            f"до {MAX_BUFFER_SIZE:g} мм."
        )
    if number < MIN_BUFFER_SIZE or number > MAX_BUFFER_SIZE:
        raise ValueError(
            f"Толщина обводки текста должна быть от {MIN_BUFFER_SIZE:g} "
            f"до {MAX_BUFFER_SIZE:g} мм."
        )
    return number


def is_enabled(params: dict[str, Any]) -> bool:
    value = params.get("enabled")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in FALSE_WORDS
    return bool(value)


def font_size(value: Any) -> float:
    if value is None:
        return DEFAULT_SIZE
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Размер шрифта задаётся числом от {MIN_SIZE:g} до {MAX_SIZE:g}.")
    if number < MIN_SIZE or number > MAX_SIZE:
        raise ValueError(f"Размер шрифта должен быть от {MIN_SIZE:g} до {MAX_SIZE:g} пунктов.")
    return number
