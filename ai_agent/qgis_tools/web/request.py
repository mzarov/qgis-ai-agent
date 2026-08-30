from typing import Any
from urllib.parse import urlsplit

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkProxy, QNetworkProxyFactory, QNetworkProxyQuery, QNetworkRequest

from ai_agent.qgis_tools.web.response import integer
from ai_agent.qgis_tools.web.url_policy import canonical_host, host_header, pinned_url

USER_AGENT = "AI Agent (QGIS plugin; https://github.com/mzarov/qgis-ai-agent)"
TIMEOUT_MS = 30_000


def network_request(
    url: str,
    headers: dict[str, str],
    *,
    address: str,
    manager: Any | None = None,
) -> QNetworkRequest:
    parsed = urlsplit(url)
    host = canonical_host(parsed.hostname or "")
    port = parsed.port
    active_manager = manager or QgsNetworkAccessManager.instance()
    destination = request_destination(active_manager, url, address)
    request = QNetworkRequest(QUrl(destination))
    if destination != url:
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


def request_destination(manager: Any, url: str, address: str) -> str:
    destination = pinned_url(url, address)
    if request_uses_proxy(manager, url):
        return url
    require_consistent_proxy_route(manager, url, destination)
    return destination


def request_uses_proxy(manager: Any, url: str) -> bool:
    routes = proxy_routes(manager, url)
    if not routes:
        return False
    direct = {
        integer(QNetworkProxy.ProxyType.DefaultProxy),
        integer(QNetworkProxy.ProxyType.NoProxy),
    }
    return routes[0][0] not in direct


def require_consistent_proxy_route(manager: Any, original_url: str, destination: str) -> None:
    if proxy_routes(manager, original_url) != proxy_routes(manager, destination):
        raise ValueError(
            "QGIS proxy rules choose different routes for the host and its validated IP; "
            "the web request was blocked instead of bypassing those rules."
        )


def proxy_routes(manager: Any, url: str) -> tuple[tuple[int, str, int, str], ...]:
    configured = manager.proxy()
    if configured.type() != QNetworkProxy.ProxyType.DefaultProxy:
        proxies = [configured]
    else:
        query = QNetworkProxyQuery(QUrl(url))
        factory = manager.proxyFactory()
        proxies = factory.queryProxy(query) if factory is not None else QNetworkProxyFactory.proxyForQuery(query)
    return tuple(
        (integer(proxy.type()), proxy.hostName().lower(), int(proxy.port()), proxy.user()) for proxy in proxies
    )
