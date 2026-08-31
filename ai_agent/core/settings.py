import hashlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from qgis.core import QgsSettings

from ai_agent.config import geocoder
from ai_agent.core import credentials

SETTINGS_PREFIX = "ai_agent"
CREDENTIAL_SCOPE_PREFIX = "api_key:"

DEFAULT_API_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DIALECT_AUTO = "auto"
AUTH_TYPE_BEARER = "Bearer"
AUTH_TYPE_OAUTH = "OAuth"
GEOCODER_DISABLED = geocoder.GEOCODER_DISABLED
GEOCODER_PHOTON = geocoder.GEOCODER_PHOTON
GEOCODER_NOMINATIM = geocoder.GEOCODER_NOMINATIM
GEOCODER_PHOTON_URL = geocoder.GEOCODER_PHOTON_URL
DEFAULT_GEOCODER_PROVIDER = geocoder.DEFAULT_GEOCODER_PROVIDER

FALSE_WORDS = ("false", "0", "no", "off")
TRUE_WORDS = ("true", "1", "yes", "on")
SCOPE_KEY_LENGTH = 24


def _read(key: str, default: str) -> str:
    value = QgsSettings().value(f"{SETTINGS_PREFIX}/{key}", default, type=str)
    return value if isinstance(value, str) and value else default


def _write(key: str, value: str) -> None:
    settings = QgsSettings()
    settings.setValue(f"{SETTINGS_PREFIX}/{key}", value)
    settings.sync()


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() not in FALSE_WORDS


def _as_opt_in_bool(value: Any) -> bool:
    return str(value).strip().lower() in TRUE_WORDS


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


def get_geocoder_provider() -> str:
    return geocoder.get_provider()


def set_geocoder_provider(value: str | None) -> None:
    geocoder.set_provider(value)


def get_custom_nominatim_url() -> str:
    return geocoder.get_custom_url()


def set_custom_nominatim_url(value: str | None) -> None:
    geocoder.set_custom_url(value)


def get_geocoder_url() -> str:
    return geocoder.get_url()


def get_verify_ssl(url: str | None = None) -> bool:
    endpoint = (url if url is not None else get_api_url()) or ""
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/verify_ssl/{_url_settings_key(endpoint)}")
    return True if stored is None else _as_bool(stored)


def set_verify_ssl(value: bool, url: str | None = None) -> None:
    endpoint = (url if url is not None else get_api_url()) or ""
    _write(f"verify_ssl/{_url_settings_key(endpoint)}", "true" if value else "false")


def get_data_sharing_consent(url: str | None = None) -> bool:
    endpoint = (url if url is not None else get_api_url()) or ""
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/data_sharing_consent/{_url_settings_key(endpoint)}")
    return False if stored is None else _as_opt_in_bool(stored)


def set_data_sharing_consent(value: bool, url: str | None = None) -> None:
    endpoint = (url if url is not None else get_api_url()) or ""
    _write(f"data_sharing_consent/{_url_settings_key(endpoint)}", "true" if value else "false")


def get_allow_sensitive_data(url: str | None = None) -> bool:
    endpoint = (url if url is not None else get_api_url()) or ""
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/allow_sensitive_data/{_url_settings_key(endpoint)}")
    return False if stored is None else _as_opt_in_bool(stored)


def set_allow_sensitive_data(value: bool, url: str | None = None) -> None:
    endpoint = (url if url is not None else get_api_url()) or ""
    _write(f"allow_sensitive_data/{_url_settings_key(endpoint)}", "true" if value else "false")


DEFAULT_TOKEN_BUDGET = 300000


def get_token_budget() -> int:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/token_budget")
    if stored is None:
        return DEFAULT_TOKEN_BUDGET
    try:
        return max(0, int(stored))
    except (TypeError, ValueError):
        return DEFAULT_TOKEN_BUDGET


def set_token_budget(value: int) -> None:
    _write("token_budget", str(max(0, int(value))))


def get_write_run_journal() -> bool:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/write_run_journal")
    return False if stored is None else _as_bool(stored)


def set_write_run_journal(value: bool) -> None:
    _write("write_run_journal", "true" if value else "false")


def get_verify_after_apply() -> bool:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/verify_after_apply")
    return True if stored is None else _as_bool(stored)


def set_verify_after_apply(value: bool) -> None:
    _write("verify_after_apply", "true" if value else "false")


def get_supports_images(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/supports_images/{_capability_settings_key(url, model, dialect)}")
    return None if stored is None else _as_bool(stored)


def set_supports_images(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write(f"supports_images/{_capability_settings_key(url, model, dialect)}", "true" if value else "false")


def get_thinking_budget() -> int:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/thinking_budget")
    if stored is None:
        return 0
    try:
        return max(0, int(stored))
    except (TypeError, ValueError):
        return 0


def set_thinking_budget(value: int) -> None:
    _write("thinking_budget", str(max(0, int(value or 0))))


def get_supports_thinking(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/supports_thinking/{_capability_settings_key(url, model, dialect)}")
    return None if stored is None else _as_bool(stored)


def set_supports_thinking(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write(f"supports_thinking/{_capability_settings_key(url, model, dialect)}", "true" if value else "false")


def get_supports_streaming(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    key = _capability_settings_key(url, model, dialect)
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/supports_streaming/{key}")
    return None if stored is None else _as_bool(stored)


def set_supports_streaming(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write(f"supports_streaming/{_capability_settings_key(url, model, dialect)}", "true" if value else "false")


def get_supports_tools(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    stored = QgsSettings().value(f"{SETTINGS_PREFIX}/supports_tools/{_capability_settings_key(url, model, dialect)}")
    return None if stored is None else _as_bool(stored)


def set_supports_tools(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write(f"supports_tools/{_capability_settings_key(url, model, dialect)}", "true" if value else "false")


def get_api_key(url: str | None = None, dialect: str | None = None) -> str:
    endpoint = (url if url is not None else get_api_url()) or ""
    return credentials.read(_credential_account(endpoint, dialect))


def set_api_key(value: str, url: str | None = None, dialect: str | None = None) -> None:
    endpoint = (url if url is not None else get_api_url()) or ""
    secret = (value or "").strip()
    if not secret:
        delete_api_key(endpoint, dialect)
        return
    credentials.write(_credential_account(endpoint, dialect), secret)


def delete_api_key(url: str | None = None, dialect: str | None = None) -> None:
    endpoint = (url if url is not None else get_api_url()) or ""
    credentials.remove(_credential_account(endpoint, dialect))


def get_credential_store_error() -> str:
    return credentials.last_error()


def credential_store_failure_message() -> str:
    return credentials.failure_message()


def _url_settings_key(url: str) -> str:
    normalized = _normalized_url(url)
    return _scope_digest(normalized)


def _capability_settings_key(url: str, model: str | None, dialect: str | None) -> str:
    scope = "\n".join(
        (
            _normalized_url(url),
            (model if model is not None else get_model()).strip(),
            _resolved_dialect(url, dialect),
        )
    )
    return _scope_digest(scope)


def _credential_account(url: str, dialect: str | None) -> str:
    scope = "\n".join((_normalized_url(url), _resolved_dialect(url, dialect)))
    return CREDENTIAL_SCOPE_PREFIX + _scope_digest(scope)


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:SCOPE_KEY_LENGTH]


def _normalized_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


def _resolved_dialect(url: str, dialect: str | None) -> str:
    from ai_agent.core.llm.dialects import resolve

    return resolve(url, dialect if dialect is not None else get_dialect())
