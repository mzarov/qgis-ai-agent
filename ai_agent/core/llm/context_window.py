"""How many tokens the model can read at once, and when the conversation gets compacted.

No standard API reports it. A size set in Settings wins; then what the server
itself said at the last connection test (OpenAI-style `/models` entries,
Ollama's `num_ctx`, LM Studio's `/api/v0/models`); then a guess from the
model's name; then a cautious default. Detection only talks to the configured
server: the key goes nowhere else.
"""

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray

from ai_agent.core.llm.client import build_network_request, build_request
from ai_agent.core.settings import get_context_window, get_detected_context_window

DEFAULT_WINDOW = 128_000
# Compact before a request once the last one took this share of the window, as Codex does.
AUTO_COMPACT_SHARE = 0.9
DETECT_TIMEOUT = 5
OLLAMA_PORT = 11434
LMSTUDIO_PORT = 1234
WINDOW_KEYS = ("context_length", "max_model_len", "context_window", "max_context_length")
# The first fragment found in the model's name decides; more specific names come first.
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
    """Ask the server for the model's window; 0 when it does not say. Never raises.

    Runs on the connection-test thread, so the blocking requests stay off the UI.
    """
    try:
        endpoint, headers, model = build_request(
            overrides.get("url_override"),
            overrides.get("key_override"),
            overrides.get("auth_type_override"),
            overrides.get("model_override"),
            overrides.get("dialect_override"),
        )
    except Exception:
        return 0
    base = str(overrides.get("url_override") or "").rstrip("/") or endpoint.rsplit("/", 2)[0]
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


def _from_models_list(base: str, headers: dict[str, str], model: str, verify: Any, feedback: Any) -> int:
    listing = _request(f"{base}/models", headers, verify, feedback)
    for entry in listing.get("data") or []:
        if isinstance(entry, dict) and entry.get("id") == model:
            return _window_in(entry) or _window_in(entry.get("top_provider") or {})
    return 0


def _from_ollama(base: str, headers: dict[str, str], model: str, verify: Any, feedback: Any) -> int:
    """Ollama's runtime `num_ctx` when the model sets one; its trained maximum would overstate.

    Without `num_ctx` Ollama runs a small default window and truncates silently, but
    compacting against that default would compact on every request: the name guess stays.
    """
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
    request = build_network_request(url, headers, verify, DETECT_TIMEOUT)
    caller = QgsBlockingNetworkRequest()
    if body is None:
        error = caller.get(request, False, feedback)
    else:
        error = caller.post(request, QByteArray(json.dumps(body).encode("utf-8")), False, feedback)
    if error != QgsBlockingNetworkRequest.ErrorCode.NoError:
        return {}
    parsed = json.loads(bytes(caller.reply().content()).decode("utf-8", errors="replace") or "{}")
    return parsed if isinstance(parsed, dict) else {}
