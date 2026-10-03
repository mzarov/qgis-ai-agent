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


def _stored(key: str) -> Any:
    return QgsSettings().value(f"{SETTINGS_PREFIX}/{key}")


def _read_flag(key: str, default: bool, opt_in: bool = False) -> bool:
    """A switch: unset reads as `default`. Any stored value but a no is a yes, except for an
    opt-in (consent, reasoning), which takes nothing short of an explicit yes."""
    stored = _stored(key)
    if stored is None:
        return default
    word = str(stored).strip().lower()
    return word in TRUE_WORDS if opt_in else word not in FALSE_WORDS


def _write_flag(key: str, value: bool) -> None:
    _write(key, "true" if value else "false")


def _read_count(key: str, default: int = 0) -> int:
    """A non-negative whole number; anything unreadable reads as `default`."""
    stored = _stored(key)
    if stored is None:
        return default
    try:
        return max(0, int(stored))
    except (TypeError, ValueError):
        return default


def _write_count(key: str, value: int) -> None:
    _write(key, str(max(0, int(value or 0))))


def _read_capability(name: str, url: str, model: str | None, dialect: str | None) -> bool | None:
    """What was detected about an endpoint and model: None until a request found out."""
    stored = _stored(f"{name}/{_capability_settings_key(url, model, dialect)}")
    return None if stored is None else str(stored).strip().lower() not in FALSE_WORDS


def _write_capability(name: str, value: bool, url: str, model: str | None, dialect: str | None) -> None:
    _write_flag(f"{name}/{_capability_settings_key(url, model, dialect)}", value)


def _endpoint(url: str | None) -> str:
    return (url if url is not None else get_api_url()) or ""


# Connection


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


def get_verify_ssl(url: str | None = None) -> bool:
    return _read_flag(f"verify_ssl/{_url_settings_key(_endpoint(url))}", True)


def set_verify_ssl(value: bool, url: str | None = None) -> None:
    _write_flag(f"verify_ssl/{_url_settings_key(_endpoint(url))}", value)


def get_data_sharing_consent(url: str | None = None) -> bool:
    return _read_flag(f"data_sharing_consent/{_url_settings_key(_endpoint(url))}", False, opt_in=True)


def set_data_sharing_consent(value: bool, url: str | None = None) -> None:
    _write_flag(f"data_sharing_consent/{_url_settings_key(_endpoint(url))}", value)


# Geocoding lives in config/, shared with the tools.


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


# How the agent works

DEFAULT_TOKEN_BUDGET = 300000
WORK_MODE_ASK = "ask"
WORK_MODE_AUTO = "auto"
WORK_MODES = (WORK_MODE_ASK, WORK_MODE_AUTO)


def get_token_budget() -> int:
    return _read_count("token_budget", DEFAULT_TOKEN_BUDGET)


def set_token_budget(value: int) -> None:
    _write_count("token_budget", value)


def get_write_run_journal() -> bool:
    return _read_flag("write_run_journal", False)


def set_write_run_journal(value: bool) -> None:
    _write_flag("write_run_journal", value)


def get_verify_after_apply() -> bool:
    return _read_flag("verify_after_apply", True)


def set_verify_after_apply(value: bool) -> None:
    _write_flag("verify_after_apply", value)


def get_thinking_budget() -> int:
    return _read_count("thinking_budget")


def set_thinking_budget(value: int) -> None:
    _write_count("thinking_budget", value)


def get_reasoning_enabled() -> bool:
    """Whether OpenAI-compatible endpoints are asked to reason; Anthropic uses the thinking budget."""
    return _read_flag("reasoning_enabled", False, opt_in=True)


def set_reasoning_enabled(
    value: bool, url: str | None = None, model: str | None = None, dialect: str | None = None
) -> None:
    """Store the switch; turning it on forgets a remembered refusal so the endpoint is asked again."""
    if value and not get_reasoning_enabled():
        QgsSettings().remove(
            f"{SETTINGS_PREFIX}/supports_thinking/{_capability_settings_key(_endpoint(url), model, dialect)}"
        )
    _write_flag("reasoning_enabled", value)


def get_work_mode() -> str:
    """How prepared changes are applied: `ask` waits for the button, `auto` applies them itself."""
    stored = _stored("work_mode")
    return stored if isinstance(stored, str) and stored in WORK_MODES else WORK_MODE_ASK


def set_work_mode(mode: str) -> None:
    _write("work_mode", mode if mode in WORK_MODES else WORK_MODE_ASK)


def get_auto_apply() -> bool:
    """Auto mode: prepared batches apply without the button, destructive ones excepted."""
    return get_work_mode() == WORK_MODE_AUTO


def get_context_window() -> int:
    """The model's context window set by hand, in tokens; 0 lets the plugin find it."""
    return _read_count("context_window")


def set_context_window(tokens: int) -> None:
    _write_count("context_window", tokens)


# What was detected about an endpoint and model; a connection test forgets it all.

CAPABILITIES = ("supports_images", "supports_thinking", "supports_streaming", "supports_tools", "context_detected")


def get_supports_images(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    return _read_capability("supports_images", url, model, dialect)


def set_supports_images(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write_capability("supports_images", value, url, model, dialect)


def get_supports_thinking(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    return _read_capability("supports_thinking", url, model, dialect)


def set_supports_thinking(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write_capability("supports_thinking", value, url, model, dialect)


def get_supports_streaming(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    return _read_capability("supports_streaming", url, model, dialect)


def set_supports_streaming(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write_capability("supports_streaming", value, url, model, dialect)


def get_supports_tools(url: str, model: str | None = None, dialect: str | None = None) -> bool | None:
    return _read_capability("supports_tools", url, model, dialect)


def set_supports_tools(url: str, value: bool, model: str | None = None, dialect: str | None = None) -> None:
    _write_capability("supports_tools", value, url, model, dialect)


def get_detected_context_window(url: str, model: str | None = None, dialect: str | None = None) -> int:
    return _read_count(f"context_detected/{_capability_settings_key(url, model, dialect)}")


def set_detected_context_window(tokens: int, url: str, model: str | None = None, dialect: str | None = None) -> None:
    _write_count(f"context_detected/{_capability_settings_key(url, model, dialect)}", tokens)


def reset_capabilities(url: str, model: str | None = None, dialect: str | None = None) -> None:
    """Forget what was detected about an endpoint, so the next run detects it afresh.

    Detection remembers refusals for good; a successful connection test is the
    user's way to say "try everything again".
    """
    settings = QgsSettings()
    key = _capability_settings_key(url, model, dialect)
    for capability in CAPABILITIES:
        settings.remove(f"{SETTINGS_PREFIX}/{capability}/{key}")
    settings.sync()


# Keys live in the QGIS authentication database, never here.


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
