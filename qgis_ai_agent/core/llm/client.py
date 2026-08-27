from typing import Any

from qgis_ai_agent.core.llm.dialects import headers_for, host_of, path_for, resolve
from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_dialect,
    get_model,
    get_verify_ssl,
)

REQUESTS_INSTALL_MSG = (
    "Для запросов к API нужна библиотека requests. "
    "Установите её в Python QGIS. См. документацию плагина (раздел «Зависимости»)."
)
DEFAULT_TIMEOUT = 120
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal")
MISSING_KEY_MSG = (
    "Не задан API-ключ. Укажите его в Настройках — или подключитесь к локальной "
    "модели: для адреса на localhost ключ не нужен."
)
ERROR_BODY_LIMIT = 300


class ApiResponseError(RuntimeError):
    def __init__(self, status_code: int, body: str, message: str | None = None):
        super().__init__(message or f"API вернул {status_code}: {body[:ERROR_BODY_LIMIT]}")
        self.status_code = status_code
        self.body = body


_SESSION = None


def get_session() -> Any:
    global _SESSION
    if _SESSION is None:
        try:
            import requests
        except ImportError:
            raise RuntimeError(REQUESTS_INSTALL_MSG)
        _SESSION = requests.Session()
    return _SESSION


def resolve_endpoint(url_override: str | None = None) -> str:
    url = (url_override or get_api_url() or "").strip().rstrip("/")
    if not url:
        raise ValueError("Не задан URL API. Укажите его в Настройках.")
    return url


def build_request(
    url_override: str | None = None,
    key_override: str | None = None,
    auth_type_override: str | None = None,
    model_override: str | None = None,
    dialect_override: str | None = None,
) -> tuple[str, dict[str, str], str]:
    url = resolve_endpoint(url_override)
    key = ((key_override if key_override is not None else get_api_key()) or "").strip()
    if not key and not is_local(url):
        raise ValueError(MISSING_KEY_MSG)
    chosen = dialect_override if dialect_override is not None else get_dialect()
    dialect = resolve(url, chosen)
    auth_type = auth_type_override if auth_type_override is not None else get_auth_type()
    headers = headers_for(dialect, key, auth_type, url)
    model = (model_override if model_override is not None else get_model()) or ""
    return url + path_for(dialect), headers, model


def is_local(url: str) -> bool:
    host = host_of(url)
    return host in LOCAL_HOSTS or host.endswith(".local")


def post_json(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
    verify_override: bool | None = None,
) -> dict[str, Any]:
    session = get_session()
    verify_ssl = bool(verify_override) if verify_override is not None else get_verify_ssl()
    response = session.post(
        endpoint, json=body, headers=headers, timeout=timeout, verify=verify_ssl
    )
    if response.status_code >= 400:
        raise ApiResponseError(response.status_code, response.text or "")
    return response.json()


def post_chat_completion(
    messages: list[dict[str, Any]],
    extra_body: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    **overrides: Any,
) -> dict[str, Any]:
    endpoint, headers, model = build_request(
        overrides.get("url_override"),
        overrides.get("key_override"),
        overrides.get("auth_type_override"),
        overrides.get("model_override"),
        overrides.get("dialect_override"),
    )
    body = {"model": model, "messages": messages, "stream": False}
    if extra_body:
        body.update(extra_body)
    return post_json(endpoint, headers, body, timeout, overrides.get("verify_override"))


def chat(messages: list[dict[str, Any]], timeout: int = 60, **overrides: Any) -> str:
    data = post_chat_completion(messages, timeout=timeout, **overrides)
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Пустой ответ API.")
    return ((choices[0].get("message") or {}).get("content") or "").strip()
