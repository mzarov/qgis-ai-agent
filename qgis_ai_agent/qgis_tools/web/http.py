import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QThread, QTimer, QUrl
from qgis.PyQt.QtNetwork import QHostInfo, QNetworkProxy, QNetworkProxyFactory, QNetworkProxyQuery, QNetworkRequest

from qgis_ai_agent.qgis_tools.web.response import (
    content_type_of as _content_type_of,
)
from qgis_ai_agent.qgis_tools.web.response import (
    failure_of as _failure_of,
)
from qgis_ai_agent.qgis_tools.web.response import (
    integer as _integer,
)
from qgis_ai_agent.qgis_tools.web.response import (
    redirect_of,
)
from qgis_ai_agent.qgis_tools.web.url_policy import (
    MAX_URL_CHARS,
    address_sort_key,
    canonical_host,
    has_secret_query,
    host_header,
    is_public_address,
    netloc,
    origin,
    pinned_url,
    require_allowed_host_syntax,
    safe_url_label,
    unsafe_text_control,
)

USER_AGENT = "qgis-ai-agent (QGIS plugin; https://github.com/mzarov/qgis-ai-agent)"
MAX_BODY_BYTES = 2_000_000
TIMEOUT_MS = 30_000
DNS_TIMEOUT_MS = 10_000
MAX_REDIRECTS = 3
MAX_LOCATION_BYTES = 8_192
FETCH_FAILED = "Could not fetch {url}: {reason}."
PRIVATE_ADDRESS = "The web tool does not access local, private, link-local or reserved network addresses."
HTTPS_REQUIRED = "Web tools require an https URL."
CROSS_ORIGIN_REDIRECT = "A cross-origin redirect from {source} was blocked."
REQUEST_CANCELLED = "The web request was cancelled."
STATUS_ATTRIBUTE = QNetworkRequest.Attribute.HttpStatusCodeAttribute
_ACTIVE_REPLIES: list[Any] = []
_ACTIVE_LOOKUPS: dict[int, Any] = {}
_CANCEL_EPOCH = 0


class RequestCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class _Hop:
    body: bytes
    status: int
    redirect: str = ""
    error: str = ""
    content_type: str = ""


def cancellation_epoch() -> int:
    return _CANCEL_EPOCH


def guard_not_cancelled(epoch: int) -> None:
    if epoch != _CANCEL_EPOCH:
        raise RequestCancelled(REQUEST_CANCELLED)


def checked_url(raw: Any, *, resolve: bool = True) -> str:
    epoch = cancellation_epoch()
    guard_not_cancelled(epoch)
    url = str(raw or "").strip()
    if not url:
        raise ValueError("The URL is empty.")
    if len(url) > MAX_URL_CHARS:
        raise ValueError(f"The URL must not exceed {MAX_URL_CHARS} characters.")
    if unsafe_text_control(url):
        raise ValueError("The URL contains control or formatting characters.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("The URL is malformed; check its host, brackets and port.") from None
    if parsed.scheme.lower() != "https":
        raise ValueError(HTTPS_REQUIRED)
    if not host:
        raise ValueError("The URL needs a host name.")
    host = canonical_host(host)
    keys = {key.strip().lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if parsed.username is not None or parsed.password is not None or has_secret_query(keys):
        raise ValueError("Do not put credentials or signed-access parameters in a web URL.")
    require_allowed_host_syntax(host, PRIVATE_ADDRESS)
    if resolve:
        _require_public_host(host, port or 443, epoch=epoch)
    guard_not_cancelled(epoch)
    shown_host = netloc(host, port)
    return urlunsplit(("https", shown_host, parsed.path or "/", parsed.query, ""))


def get_text(
    url: str,
    extra_headers: dict[str, str] | None = None,
    *,
    epoch: int | None = None,
) -> str:
    return get_document(url, extra_headers, epoch=epoch)[0]


def get_document(
    url: str,
    extra_headers: dict[str, str] | None = None,
    *,
    epoch: int | None = None,
) -> tuple[str, str]:
    request_epoch = cancellation_epoch() if epoch is None else epoch
    guard_not_cancelled(request_epoch)
    current = checked_url(url, resolve=False)
    guard_not_cancelled(request_epoch)
    approved_origin = origin(current)
    parsed = urlsplit(current)
    addresses = _require_public_host(parsed.hostname or "", parsed.port or 443, epoch=request_epoch)
    address = addresses[0]
    for redirect_count in range(MAX_REDIRECTS + 1):
        guard_not_cancelled(request_epoch)
        hop = _download_once(current, extra_headers or {}, address=address, epoch=request_epoch)
        guard_not_cancelled(request_epoch)
        if hop.redirect and 300 <= hop.status < 400:
            if redirect_count >= MAX_REDIRECTS:
                raise ValueError(f"Too many redirects while fetching {safe_url_label(current)}.")
            redirected = checked_url(urljoin(current, hop.redirect), resolve=False)
            if origin(redirected) != approved_origin:
                raise ValueError(CROSS_ORIGIN_REDIRECT.format(source=safe_url_label(current)))
            current = redirected
            continue
        if hop.status >= 400:
            raise ValueError(FETCH_FAILED.format(url=safe_url_label(current), reason=f"HTTP {hop.status}"))
        if 300 <= hop.status < 400:
            raise ValueError(FETCH_FAILED.format(url=safe_url_label(current), reason="redirect without a target"))
        if hop.error:
            raise ValueError(FETCH_FAILED.format(url=safe_url_label(current), reason=hop.error))
        guard_not_cancelled(request_epoch)
        return hop.body.decode("utf-8", errors="replace"), hop.content_type
    raise ValueError(f"Too many redirects while fetching {safe_url_label(current)}.")


def cancel_active_requests() -> None:
    global _CANCEL_EPOCH
    _CANCEL_EPOCH += 1
    for lookup_id, loop in tuple(_ACTIVE_LOOKUPS.items()):
        try:
            QHostInfo.abortHostLookup(lookup_id)
        except (AttributeError, RuntimeError):
            pass
        try:
            loop.quit()
        except (AttributeError, RuntimeError):
            pass
    for reply in tuple(_ACTIVE_REPLIES):
        try:
            reply.abort()
        except (AttributeError, RuntimeError):
            pass


def confirmation_url_label(url: str) -> str:
    try:
        return checked_url(url, resolve=False)
    except ValueError:
        return safe_url_label(url)


def _download_once(url: str, headers: dict[str, str], *, address: str, epoch: int) -> _Hop:
    guard_not_cancelled(epoch)
    request = _network_request(url, headers, address=address)
    guard_not_cancelled(epoch)
    manager = QgsNetworkAccessManager.instance()
    _require_consistent_proxy_route(manager, url, pinned_url(url, address))
    guard_not_cancelled(epoch)
    reply = manager.get(request)
    _ACTIVE_REPLIES.append(reply)
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(TIMEOUT_MS)
    body = bytearray()
    state = {"too_large": False, "timed_out": False}

    def drain() -> None:
        if state["timed_out"] or not reply.isOpen():
            return
        remaining = MAX_BODY_BYTES + 1 - len(body)
        if remaining <= 0:
            state["too_large"] = True
        else:
            chunk = reply.read(remaining)
            if chunk is not None:
                body.extend(bytes(chunk))
            state["too_large"] = len(body) > MAX_BODY_BYTES
        if state["too_large"]:
            reply.abort()
            loop.quit()

    def time_out() -> None:
        state["timed_out"] = True
        reply.abort()
        loop.quit()

    reply.readyRead.connect(drain)
    reply.finished.connect(loop.quit)
    timer.timeout.connect(time_out)
    try:
        timer.start()
        if not reply.isFinished():
            loop.exec()
        drain()
        guard_not_cancelled(epoch)
        if state["too_large"]:
            raise ValueError(f"The response from {safe_url_label(url)} exceeded 2 MB and was discarded.")
        if state["timed_out"]:
            raise ValueError(FETCH_FAILED.format(url=safe_url_label(url), reason="timed out"))
        status = _status_of(reply)
        redirect = _redirect_of(reply) if 300 <= status < 400 else ""
        return _Hop(
            body=bytes(body),
            status=status,
            redirect=redirect,
            error="" if redirect else _failure_of(reply),
            content_type=_content_type_of(reply),
        )
    finally:
        timer.stop()
        if reply in _ACTIVE_REPLIES:
            _ACTIVE_REPLIES.remove(reply)
        reply.deleteLater()


def _network_request(url: str, headers: dict[str, str], *, address: str) -> QNetworkRequest:
    parsed = urlsplit(url)
    host = canonical_host(parsed.hostname or "")
    port = parsed.port
    destination = pinned_url(url, address)
    request = QNetworkRequest(QUrl(destination))
    if not hasattr(request, "setPeerVerifyName"):
        raise ValueError("This QGIS/Qt build cannot safely verify a pinned HTTPS web request.")
    request.setPeerVerifyName(host)
    for name, value in headers.items():
        if name.strip().lower() not in {"host", "accept-encoding"}:
            request.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    request.setRawHeader(b"Host", host_header(host, port).encode("ascii"))
    request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))
    request.setRawHeader(b"Accept-Language", b"ru,en;q=0.8")
    request.setRawHeader(b"Accept-Encoding", b"identity")
    request.setAttribute(
        QNetworkRequest.Attribute.RedirectPolicyAttribute,
        QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QNetworkRequest.CacheLoadControl.AlwaysNetwork,
    )
    request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
    request.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
    request.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute, QNetworkRequest.LoadControl.Manual)
    request.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute, QNetworkRequest.LoadControl.Manual)
    request.setAttribute(QNetworkRequest.Attribute.AuthenticationReuseAttribute, QNetworkRequest.LoadControl.Manual)
    request.setTransferTimeout(TIMEOUT_MS)
    return request


def _require_public_host(host: str, port: int, *, epoch: int | None = None) -> tuple[str, ...]:
    request_epoch = cancellation_epoch() if epoch is None else epoch
    guard_not_cancelled(request_epoch)
    normalized = (host or "").strip().lower().rstrip(".")
    addresses = _resolved_addresses(normalized, port, epoch=request_epoch)
    guard_not_cancelled(request_epoch)
    if not addresses:
        raise ValueError(f"The host '{normalized}' could not be resolved.")
    parsed_addresses = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(str(address))
        except ValueError:
            raise ValueError(f"The host '{normalized}' resolved to an invalid address.") from None
        if not is_public_address(parsed):
            raise ValueError(PRIVATE_ADDRESS)
        parsed_addresses.append(parsed)
    return tuple(str(address) for address in sorted(set(parsed_addresses), key=address_sort_key))


def _resolved_addresses(host: str, port: int, *, epoch: int | None = None) -> tuple[str, ...]:
    del port  # QHostInfo resolves host addresses without opening a socket.
    request_epoch = cancellation_epoch() if epoch is None else epoch
    guard_not_cancelled(request_epoch)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return (str(literal),)
    addresses = _qt_lookup_addresses(host, epoch=request_epoch)
    guard_not_cancelled(request_epoch)
    return tuple(addresses)


def _qt_lookup_addresses(host: str, *, epoch: int) -> tuple[str, ...]:
    guard_not_cancelled(epoch)
    application = QCoreApplication.instance()
    if application is None or not application:
        raise ValueError("Web DNS lookup requires the running QGIS application.")
    if QThread.currentThread() is not application.thread():
        raise ValueError("Web DNS lookup must run on the QGIS main thread.")

    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(DNS_TIMEOUT_MS)
    state: dict[str, Any] = {"answers": (), "done": False, "timed_out": False}
    lookup_id = -1

    def resolved(info: Any) -> None:
        if info.error() == QHostInfo.HostInfoError.NoError:
            state["answers"] = tuple(address.toString() for address in info.addresses())
        state["done"] = True
        loop.quit()

    def time_out() -> None:
        state["timed_out"] = True
        if lookup_id >= 0:
            QHostInfo.abortHostLookup(lookup_id)
        loop.quit()

    timer.timeout.connect(time_out)
    lookup_id = QHostInfo.lookupHost(host, resolved)
    _ACTIVE_LOOKUPS[lookup_id] = loop
    timer.start()
    try:
        guard_not_cancelled(epoch)
        if not state["done"]:
            loop.exec()
        guard_not_cancelled(epoch)
        if state["timed_out"]:
            raise ValueError(f"DNS lookup for '{host}' timed out.")
        return tuple(state["answers"])
    finally:
        timer.stop()
        _ACTIVE_LOOKUPS.pop(lookup_id, None)
        if not state["done"]:
            try:
                QHostInfo.abortHostLookup(lookup_id)
            except (AttributeError, RuntimeError):
                pass


def _require_consistent_proxy_route(manager: Any, original_url: str, pinned_url: str) -> None:
    if _proxy_routes(manager, original_url) != _proxy_routes(manager, pinned_url):
        raise ValueError(
            "QGIS proxy rules choose different routes for the host and its validated IP; "
            "the web request was blocked instead of bypassing those rules."
        )


def _proxy_routes(manager: Any, url: str) -> tuple[tuple[int, str, int, str], ...]:
    configured = manager.proxy()
    if configured.type() != QNetworkProxy.ProxyType.DefaultProxy:
        proxies = [configured]
    else:
        query = QNetworkProxyQuery(QUrl(url))
        factory = manager.proxyFactory()
        proxies = factory.queryProxy(query) if factory is not None else QNetworkProxyFactory.proxyForQuery(query)
    return tuple(
        (_integer(proxy.type()), proxy.hostName().lower(), int(proxy.port()), proxy.user()) for proxy in proxies
    )


def _redirect_of(reply: Any) -> str:
    return redirect_of(reply, MAX_LOCATION_BYTES)


def _status_of(reply: Any) -> int:
    try:
        return _integer(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0
