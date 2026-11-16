import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ai_agent.core.llm.client import build_network_request, build_request
from ai_agent.core.settings import get_context_window, get_detected_context_window
from ai_agent.i18n import tr
from ai_agent.qgis_tools.common.network import Answer, send

DEFAULT_WINDOW = 128_000
AUTO_COMPACT_SHARE = 0.9
DETECT_TIMEOUT = 5
OLLAMA_PORT = 11434
LMSTUDIO_PORT = 1234
WINDOW_KEYS = ("context_length", "max_model_len", "context_window", "max_context_length")
LISTING_KEYS = ("data", "models")
NAME_KEYS = ("id", "name", "model")
MAX_LISTED = 2000
MAX_NAME_CHARS = 200
REFUSED_STATUSES = (401, 403)
LIST_REFUSED = tr("The server refused the key, so it did not list its models.")
LIST_UNREACHABLE = tr("Could not reach the server to list its models.")
LIST_MISSING = tr("The server answered {0} instead of a model list.")
KNOWN_WINDOWS = (
    ("gpt-4.1", 1_047_576),
    ("gpt-5", 400_000),
    ("gpt-4o", 128_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude", 200_000),
    ("gemini", 1_048_576),
    ("kimi", 262_144),
    ("qwen", 131_072),
    ("deepseek", 128_000),
    ("glm", 128_000),
    ("llama", 128_000),
    ("mistral", 128_000),
    ("gemma", 128_000),
)


def window_for(url: str, model: str, dialect: str | None = None) -> int:
    manual = get_context_window()
    if manual:
        return manual
    detected = get_detected_context_window(url, model, dialect)
    return detected or guessed(model)


def auto_compact_at(window: int) -> int:
    return int(window * AUTO_COMPACT_SHARE)


def guessed(model: str) -> int:
    name = (model or "").lower()
    return next((size for fragment, size in KNOWN_WINDOWS if fragment in name), DEFAULT_WINDOW)


def detect(overrides: dict[str, Any]) -> int:
    try:
        base, headers, model = _server(overrides)
    except Exception:
        return 0
    verify = overrides.get("verify_override")
    feedback = overrides.get("feedback_override")
    for attempt in (_from_models_list, _from_ollama, _from_lmstudio):
        if feedback is not None and feedback.isCanceled():
            return 0
        try:
            found = attempt(base, headers, model, verify, feedback)
        except Exception:
            found = 0
        if found:
            return found
    return 0


def list_models(overrides: dict[str, Any]) -> tuple[list[str], str]:
    try:
        base, headers, _model = _server(overrides)
    except Exception as error:
        return [], str(error) or type(error).__name__
    try:
        answer = _fetch(f"{base}/models", headers, overrides.get("verify_override"), overrides.get("feedback_override"))
    except Exception:
        return [], LIST_UNREACHABLE
    if answer.status in REFUSED_STATUSES:
        return [], LIST_REFUSED
    if answer.failed or not answer.status:
        return [], LIST_MISSING.format(answer.status) if answer.status else LIST_UNREACHABLE
    return model_names(_parsed(answer)), ""


def model_names(listing: dict[str, Any]) -> list[str]:
    entries: list[Any] = next((listing[key] for key in LISTING_KEYS if isinstance(listing.get(key), list)), [])
    names = {_name_of(entry) for entry in entries[:MAX_LISTED]}
    return sorted(names - {""}, key=str.casefold)


def _name_of(entry: Any) -> str:
    if isinstance(entry, dict):
        entry = next((entry[key] for key in NAME_KEYS if isinstance(entry.get(key), str)), "")
    # A name is the server's text: one line, bounded, before it reaches a menu.
    return " ".join(entry.split())[:MAX_NAME_CHARS] if isinstance(entry, str) else ""


def _server(overrides: dict[str, Any]) -> tuple[str, dict[str, str], str]:
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
        overrides.get("extra_headers_override"),
    )
    base = str(overrides.get("url_override") or "").rstrip("/") or endpoint.rsplit("/", 2)[0]
    return base, headers, model


def _from_models_list(base: str, headers: dict[str, str], model: str, verify: Any, feedback: Any) -> int:
    listing = _request(f"{base}/models", headers, verify, feedback)
    for entry in listing.get("data") or []:
        if isinstance(entry, dict) and entry.get("id") == model:
            return _window_in(entry) or _window_in(entry.get("top_provider") or {})
    return 0


def _from_ollama(base: str, headers: dict[str, str], model: str, verify: Any, feedback: Any) -> int:
    if urlsplit(base).port != OLLAMA_PORT:
        return 0
    shown = _request(f"{_root(base)}/api/show", headers, verify, feedback, {"model": model})
    for line in str(shown.get("parameters") or "").splitlines():
        name, _, value = line.strip().partition(" ")
        if name == "num_ctx" and value.strip().isdigit():
            return int(value.strip())
    return 0


def _from_lmstudio(base: str, headers: dict[str, str], model: str, verify: Any, feedback: Any) -> int:
    if urlsplit(base).port != LMSTUDIO_PORT:
        return 0
    return _window_in(_request(f"{_root(base)}/api/v0/models/{model}", headers, verify, feedback))


def _window_in(entry: dict[str, Any]) -> int:
    for key in WINDOW_KEYS:
        try:
            value = int(entry.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _root(base: str) -> str:
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _request(
    url: str, headers: dict[str, str], verify: Any, feedback: Any, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    answer = _fetch(url, headers, verify, feedback, body)
    return {} if answer.failed else _parsed(answer)


def _fetch(url: str, headers: dict[str, str], verify: Any, feedback: Any, body: dict[str, Any] | None = None) -> Answer:
    request = build_network_request(url, headers, verify, DETECT_TIMEOUT)
    return send(request, None if body is None else json.dumps(body).encode("utf-8"), feedback)


def _parsed(answer: Answer) -> dict[str, Any]:
    try:
        parsed = json.loads(answer.body.decode("utf-8", errors="replace") or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
