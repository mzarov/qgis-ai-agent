from qgis.core import QgsSettings

PREFIX = "ai_agent"
DEFAULT_STEPS = 40
MIN_STEPS = 5
MAX_STEPS = 100
STEPS_INCREMENT = 5
DEFAULT_TOOL_SECONDS = 120
MIN_TOOL_SECONDS = 15
MAX_TOOL_SECONDS = 600
TOOL_SECONDS_INCREMENT = 15


def max_steps() -> int:
    return _read("max_steps", DEFAULT_STEPS, MIN_STEPS, MAX_STEPS)


def set_max_steps(value: int) -> None:
    _write("max_steps", _clamped(value, DEFAULT_STEPS, MIN_STEPS, MAX_STEPS))


def tool_seconds() -> int:
    return _read("tool_timeout", DEFAULT_TOOL_SECONDS, MIN_TOOL_SECONDS, MAX_TOOL_SECONDS)


def set_tool_seconds(value: int) -> None:
    _write("tool_timeout", _clamped(value, DEFAULT_TOOL_SECONDS, MIN_TOOL_SECONDS, MAX_TOOL_SECONDS))


def _read(key: str, default: int, low: int, high: int) -> int:
    return _clamped(QgsSettings().value(f"{PREFIX}/{key}", default), default, low, high)


def _clamped(raw: object, default: int, low: int, high: int) -> int:
    try:
        number = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _write(key: str, value: int) -> None:
    settings = QgsSettings()
    settings.setValue(f"{PREFIX}/{key}", value)
    settings.sync()
