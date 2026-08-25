import hashlib

from qgis.core import QgsSettings

KEYRING_SERVICE = "qgis_ai_agent"
KEYRING_KEY = "api_key"
SETTINGS_PREFIX = "qgis_ai_agent"
DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

KEYRING_FAILURE_MSG = (
    "Не удалось сохранить ключ в системном хранилище: {reason}.\n\n"
    "На Linux для этого нужен запущенный сервис секретов — gnome-keyring или KWallet. "
    "Если библиотеки keyring нет, установите её в Python QGIS: см. раздел «Зависимости» "
    "в документации плагина."
)


def get_api_url() -> str:
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/api_url", DEFAULT_API_URL, type=str)


def set_api_url(value: str | None) -> None:
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/api_url", value or DEFAULT_API_URL)


def get_model() -> str:
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/model", DEFAULT_MODEL, type=str)


def set_model(value: str | None) -> None:
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/model", value or DEFAULT_MODEL)


def get_verify_ssl() -> bool:
    s = QgsSettings()
    key = f"{SETTINGS_PREFIX}/verify_ssl"
    val = s.value(key)
    if val is None:
        return True
    sval = str(val).strip().lower()
    return sval not in ("false", "0", "no", "off")


def set_verify_ssl(value: bool) -> None:
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/verify_ssl", "false" if not value else "true")
    s.sync()


DIALECT_AUTO = "auto"


def get_dialect() -> str:
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/api_dialect", DIALECT_AUTO, type=str) or DIALECT_AUTO


def set_dialect(value: str | None) -> None:
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/api_dialect", value or DIALECT_AUTO)


AUTH_TYPE_BEARER = "Bearer"
AUTH_TYPE_OAUTH = "OAuth"


def get_auth_type() -> str:
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/auth_type", AUTH_TYPE_BEARER, type=str) or AUTH_TYPE_BEARER


def set_auth_type(value: str | None) -> None:
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/auth_type", value or AUTH_TYPE_BEARER)


def _url_settings_key(url: str) -> str:
    normalized = (url or "").strip().rstrip("/").lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]


def get_supports_tools(url: str) -> bool | None:
    s = QgsSettings()
    val = s.value(f"{SETTINGS_PREFIX}/supports_tools/{_url_settings_key(url)}")
    if val is None:
        return None
    return str(val).strip().lower() not in ("false", "0", "no", "off")


def set_supports_tools(url: str, value: bool) -> None:
    s = QgsSettings()
    s.setValue(
        f"{SETTINGS_PREFIX}/supports_tools/{_url_settings_key(url)}",
        "true" if value else "false",
    )
    s.sync()


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
