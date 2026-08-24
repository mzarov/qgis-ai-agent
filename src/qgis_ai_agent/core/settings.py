from qgis.core import QgsSettings

KEYRING_SERVICE = "qgis_ai_agent"
KEYRING_KEY = "api_key"
SETTINGS_PREFIX = "qgis_ai_agent"
DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

KEYRING_INSTALL_MSG = (
    "Для сохранения API-ключа нужна библиотека keyring. "
    "Установите её в Python QGIS. См. Настройки → Инструкция в документации плагина."
)


def get_api_url():
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/api_url", DEFAULT_API_URL, type=str)


def set_api_url(value):
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/api_url", value or DEFAULT_API_URL)


def get_model():
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/model", DEFAULT_MODEL, type=str)


def set_model(value):
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/model", value or DEFAULT_MODEL)


def get_verify_ssl():
    s = QgsSettings()
    key = f"{SETTINGS_PREFIX}/verify_ssl"
    val = s.value(key)
    if val is None:
        return True
    sval = str(val).strip().lower()
    return sval not in ("false", "0", "no", "off")


def set_verify_ssl(value):
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/verify_ssl", "false" if not value else "true")
    s.sync()


AUTH_TYPE_BEARER = "Bearer"
AUTH_TYPE_OAUTH = "OAuth"


def get_auth_type():
    s = QgsSettings()
    return s.value(f"{SETTINGS_PREFIX}/auth_type", AUTH_TYPE_BEARER, type=str) or AUTH_TYPE_BEARER


def set_auth_type(value):
    s = QgsSettings()
    s.setValue(f"{SETTINGS_PREFIX}/auth_type", value or AUTH_TYPE_BEARER)


def get_api_key():
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY) or ""
    except ImportError:
        return ""


def set_api_key(value):
    if not value:
        return
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, value)
    except ImportError:
        raise RuntimeError(KEYRING_INSTALL_MSG)
