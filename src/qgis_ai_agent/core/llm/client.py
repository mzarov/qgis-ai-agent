from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_model,
    get_verify_ssl,
)

REQUESTS_INSTALL_MSG = (
    "Для запросов к API нужна библиотека requests. "
    "Установите её в Python QGIS. См. документацию плагина (раздел «Зависимости»)."
)
DEFAULT_TIMEOUT = 120
ERROR_BODY_LIMIT = 300


class ApiResponseError(RuntimeError):
    def __init__(self, status_code, body, message=None):
        super().__init__(message or f"API вернул {status_code}: {body[:ERROR_BODY_LIMIT]}")
        self.status_code = status_code
        self.body = body


_SESSION = None


def get_session():
    global _SESSION
    if _SESSION is None:
        try:
            import requests
        except ImportError:
            raise RuntimeError(REQUESTS_INSTALL_MSG)
        _SESSION = requests.Session()
    return _SESSION


def resolve_endpoint(url_override=None):
    url = (url_override or get_api_url() or "").strip().rstrip("/")
    if not url:
        raise ValueError("Не задан URL API. Укажите его в Настройках.")
    return url


def build_request(url_override=None, key_override=None, auth_type_override=None, model_override=None):
    url = resolve_endpoint(url_override)
    key = ((key_override if key_override is not None else get_api_key()) or "").strip()
    if not key:
        raise ValueError("Не задан API-ключ. Укажите его в Настройках.")
    auth_type = auth_type_override if auth_type_override is not None else get_auth_type()
    headers = {
        "Authorization": f"{auth_type} {key}" if auth_type else f"Bearer {key}",
        "Content-Type": "application/json",
    }
    model = (model_override if model_override is not None else get_model()) or ""
    return f"{url}/chat/completions", headers, model


def post_chat_completion(
    messages,
    extra_body=None,
    timeout=DEFAULT_TIMEOUT,
    url_override=None,
    model_override=None,
    key_override=None,
    auth_type_override=None,
    verify_override=None,
):
    session = get_session()
    endpoint, headers, model = build_request(
        url_override, key_override, auth_type_override, model_override
    )
    body = {"model": model, "messages": messages, "stream": False}
    if extra_body:
        body.update(extra_body)
    verify_ssl = bool(verify_override) if verify_override is not None else get_verify_ssl()

    response = session.post(
        endpoint, json=body, headers=headers, timeout=timeout, verify=verify_ssl
    )
    if response.status_code >= 400:
        raise ApiResponseError(response.status_code, response.text or "")
    return response.json()


def chat(messages, timeout=60, **overrides):
    data = post_chat_completion(messages, timeout=timeout, **overrides)
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Пустой ответ API.")
    return ((choices[0].get("message") or {}).get("content") or "").strip()
