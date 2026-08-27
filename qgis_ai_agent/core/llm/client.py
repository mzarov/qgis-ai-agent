import json
from typing import Any

from qgis_ai_agent.i18n import tr

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis_ai_agent.core.llm.dialects import headers_for, host_of, path_for, resolve
from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_dialect,
    get_model,
    get_verify_ssl,
)

DEFAULT_TIMEOUT = 120
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal")
MISSING_KEY_MSG = (
    tr(
    "No API key. Set one in Settings — or connect to a local model: "
    "an address on localhost needs no key."
)
)
ERROR_BODY_LIMIT = 300
STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
TRANSPORT_FAILED = (
    tr(
    "Could not reach {endpoint}: {reason}. Check the address, the network and "
    "the QGIS proxy settings."
)
)


class ApiResponseError(RuntimeError):
    def __init__(self, status_code: int, body: str, message: str | None = None):
        super().__init__(message or tr("The API returned {0}: {1}").format(status_code, body[:ERROR_BODY_LIMIT]))
        self.status_code = status_code
        self.body = body


def resolve_endpoint(url_override: str | None = None) -> str:
    url = (url_override or get_api_url() or "").strip().rstrip("/")
    if not url:
        raise ValueError(tr("No API URL. Set one in Settings."))
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
    request = _build_network_request(endpoint, headers, verify_override)
    caller = QgsBlockingNetworkRequest()
    payload = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    if caller.post(request, payload) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise ConnectionError(
            TRANSPORT_FAILED.format(endpoint=endpoint, reason=_reason(caller))
        )
    reply = caller.reply()
    text = bytes(reply.content()).decode("utf-8", errors="replace")
    status = _status_of(reply)
    if status >= 400:
        raise ApiResponseError(status, text)
    return _decoded(text, status)


def _build_network_request(
    endpoint: str, headers: dict[str, str], verify_override: bool | None
) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(endpoint))
    for name, value in headers.items():
        request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    verify_ssl = bool(verify_override) if verify_override is not None else get_verify_ssl()
    if not verify_ssl:
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
    return request


def _status_of(reply: Any) -> int:
    try:
        return int(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0


def _decoded(text: str, status: int) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except ValueError:
        raise ApiResponseError(status, text, tr("The API returned non-JSON: {0}").format(text[:ERROR_BODY_LIMIT]))
    if not isinstance(parsed, dict):
        raise ApiResponseError(status, text, tr("The API returned something that is not a JSON object."))
    return parsed


def _reason(caller: Any) -> str:
    try:
        return caller.errorMessage() or tr("service unavailable")
    except Exception:
        return tr("service unavailable")


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
        raise ValueError(tr("The API returned an empty answer."))
    return ((choices[0].get("message") or {}).get("content") or "").strip()
