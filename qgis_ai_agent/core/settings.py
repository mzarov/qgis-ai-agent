import hashlib
from typing import Any

from qgis.core import QgsSettings

SETTINGS_PREFIX = "qgis_ai_agent"
KEYRING_SERVICE = "qgis_ai_agent"
KEYRING_KEY = "api_key"

DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DIALECT_AUTO = "auto"
AUTH_TYPE_BEARER = "Bearer"
AUTH_TYPE_OAUTH = "OAuth"

FALSE_WORDS = ("false", "0", "no", "off")
URL_KEY_LENGTH = 12

KEYRING_FAILURE_MSG = (
    "Не удалось сохранить ключ в системном хранилище: {reason}.\n\n"
    "На Linux для этого нужен запущенный сервис секретов — gnome-keyring или KWallet. "
    "Если библиотеки keyring нет, установите её в Python QGIS: см. раздел «Зависимости» "
    "в документации плагина."
)


def _read(key: str, default: str) -> str:
    value = QgsSettings().value(f"{SETTINGS_PREFIX}/{key}", default, type=str)
    return value or default


def _write(key: str, value: str) -> None:
    settings = QgsSettings()
    settings.setValue(f"{SETTINGS_PREFIX}/{key}", value)
    settings.sync()


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() not in FALSE_WORDS


def get_api_url() -> str:
    return _read("api_url", DEFAULT_API_URL)


def set_api_url(value: str | None) -> None:
    _write("api_url", value or DEFAULT_API_URL)


def get_model() -> str:
    return _read("model", DEFAULT_MODEL)


def set_model(value: str | None) -> None:
    _write("model", value or DEFAULT_MODEL)


def get_dialect() -> str:
    return _read("api_dialect", DIALECT_AUTO)


def set_dialect(value: str | None) -> None:
    _write("api_dialect", value or DIALECT_AUTO)


def get_auth_type() -> str:
    return _read("auth_type", AUTH_TYPE_BEARER)


def set_auth_type(value: str | None) -> None:
    _write("auth_type", value or AUTH_TYPE_BEARER)


def get_verify_ssl() -> bool:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/verify_ssl")
    return True if stored is None else _as_bool(stored)


def set_verify_ssl(value: bool) -> None:
    _write("verify_ssl", "true" if value else "false")


def get_supports_tools(url: str) -> bool | None:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/supports_tools/{_url_settings_key(url)}")
    return None if stored is None else _as_bool(stored)


def set_supports_tools(url: str, value: bool) -> None:
    _write(f"supports_tools/{_url_settings_key(url)}", "true" if value else "false")


def get_api_key() -> str:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY) or ""
    except Exception:
        return ""


def set_api_key(value: str) -> None:
    if not value:
        return
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, value)
    except Exception as error:
        raise RuntimeError(KEYRING_FAILURE_MSG.format(reason=error or type(error).__name__))


def _url_settings_key(url: str) -> str:
    normalized = (url or "").strip().rstrip("/").lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:URL_KEY_LENGTH]
