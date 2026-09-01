import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QSslSocket

from ai_agent.core.llm.dialects import (
    headers_for,
    host_of,
    is_loopback_host,
    path_for,
    resolve,
    safe_endpoint_label,
)
from ai_agent.core.settings import (
    credential_store_failure_message,
    get_api_key,
    get_api_url,
    get_auth_type,
    get_credential_store_error,
    get_dialect,
    get_model,
    get_verify_ssl,
)
from ai_agent.i18n import tr

DEFAULT_TIMEOUT = 120
MISSING_KEY_MSG = tr(
    "No API key. Set one in Settings — or connect to a local model: an address on localhost needs no key."
)
ERROR_BODY_LIMIT = 300
STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
TRANSPORT_FAILED = tr(
    "Could not reach {endpoint}: {reason}. Check the address, the network and the QGIS proxy settings."
)
URL_SECRET_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "awsaccesskeyid",
    "bearer",
    "client-secret",
    "client_secret",
    "credential",
    "credentials",
    "googleaccessid",
    "id-token",
    "id_token",
    "key",
    "password",
    "passwd",
    "pwd",
    "refresh-token",
    "refresh_token",
    "secret",
    "token",
    "access-token",
    "access_token",
    "sig",
    "signature",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-api-key",
    "x-goog-credential",
    "x-goog-signature",
}
URL_SECRET_SUFFIXES = (
    "-api-key",
    "-credential",
    "-password",
    "-secret",
    "-signature",
    "-token",
    "_api_key",
    "_credential",
    "_password",
    "_secret",
    "_signature",
    "_token",
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
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ValueError(tr("The API URL is malformed. Check its host, brackets and port.")) from None
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(tr("The API URL must use http or https."))
    try:
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise ValueError(tr("The API URL is malformed. Check its host, brackets and port.")) from None
    if not host:
        raise ValueError(tr("The API URL is malformed. Check its host, brackets and port."))
    if scheme == "http" and not is_local(url):
        raise ValueError(
            tr("A non-local model endpoint must use HTTPS. Use an SSH tunnel to localhost for a trusted LAN server.")
        )
    query_keys = {key.strip().lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    has_query_secret = any(key in URL_SECRET_KEYS or key.endswith(URL_SECRET_SUFFIXES) for key in query_keys)
    if parsed.username is not None or has_query_secret:
        raise ValueError(
            tr("Do not put credentials in the API URL. Store the provider secret in the API key field instead.")
        )
    return url


def build_request(
    url_override: str | None = None,
    key_override: str | None = None,
    auth_type_override: str | None = None,
    model_override: str | None = None,
    dialect_override: str | None = None,
) -> tuple[str, dict[str, str], str]:
    url = resolve_endpoint(url_override)
    chosen = dialect_override if dialect_override is not None else get_dialect()
    dialect = resolve(url, chosen)
    key = ((key_override if key_override is not None else get_api_key(url, dialect)) or "").strip()
    if not key and not is_local(url):
        if get_credential_store_error():
            raise RuntimeError(credential_store_failure_message())
        raise ValueError(MISSING_KEY_MSG)
    auth_type = auth_type_override if auth_type_override is not None else get_auth_type()
    headers = headers_for(dialect, key, auth_type, url)
    model = (model_override if model_override is not None else get_model()) or ""
    return url + path_for(dialect), headers, model


def is_local(url: str) -> bool:
    return is_loopback_host(host_of(url))


def post_json(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
    verify_override: bool | None = None,
    feedback: Any = None,
) -> dict[str, Any]:
    request = build_network_request(endpoint, headers, verify_override, timeout)
    caller = QgsBlockingNetworkRequest()
    payload = QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    if caller.post(request, payload, False, feedback) != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise ConnectionError(TRANSPORT_FAILED.format(endpoint=safe_endpoint_label(endpoint), reason=_reason(caller)))
    reply = caller.reply()
    text = bytes(reply.content()).decode("utf-8", errors="replace")
    status = _status_of(reply)
    if status >= 400:
        raise ApiResponseError(status, text)
    return _decoded(text, status)


def build_network_request(
    endpoint: str,
    headers: dict[str, str],
    verify_override: bool | None,
    timeout: int = DEFAULT_TIMEOUT,
) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(endpoint))
    for name, value in headers.items():
        request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    request.setAttribute(
        QNetworkRequest.Attribute.RedirectPolicyAttribute,
        QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QNetworkRequest.CacheLoadControl.AlwaysNetwork,
    )
    request.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
    request.setAttribute(
        QNetworkRequest.Attribute.CookieLoadControlAttribute,
        QNetworkRequest.LoadControl.Manual,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.CookieSaveControlAttribute,
        QNetworkRequest.LoadControl.Manual,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.AuthenticationReuseAttribute,
        QNetworkRequest.LoadControl.Manual,
    )
    if timeout > 0:
        request.setTransferTimeout(int(timeout * 1000))
    verify_ssl = bool(verify_override) if verify_override is not None else True
    if not verify_ssl:
        configuration = request.sslConfiguration()
        configuration.setPeerVerifyMode(_verify_none_mode())
        request.setSslConfiguration(configuration)
    return request


def _verify_none_mode() -> Any:
    return QSslSocket.PeerVerifyMode.VerifyNone


def _status_of(reply: Any) -> int:
    try:
        return int(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0


def _decoded(text: str, status: int) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except ValueError:
        raise ApiResponseError(
            status, text, tr("The API returned non-JSON: {0}").format(text[:ERROR_BODY_LIMIT])
        ) from None
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
    base_url = resolve_endpoint(overrides.get("url_override"))
    verify_override = overrides.get("verify_override")
    if verify_override is None:
        verify_override = get_verify_ssl(base_url)
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
    return post_json(
        endpoint,
        headers,
        body,
        timeout,
        verify_override,
        overrides.get("feedback_override"),
    )


def chat(messages: list[dict[str, Any]], timeout: int = 60, **overrides: Any) -> str:
    data = post_chat_completion(messages, timeout=timeout, **overrides)
    choices = data.get("choices") or []
    if not choices:
        raise ValueError(tr("The API returned an empty answer."))
    return ((choices[0].get("message") or {}).get("content") or "").strip()
