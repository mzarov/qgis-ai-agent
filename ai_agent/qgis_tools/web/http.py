import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QThread, QTimer
from qgis.PyQt.QtNetwork import QHostInfo, QNetworkRequest

from ai_agent.qgis_tools.web.request import TIMEOUT_MS, request_uses_proxy
from ai_agent.qgis_tools.web.request import network_request as _network_request
from ai_agent.qgis_tools.web.response import (
    content_type_of as _content_type_of,
)
from ai_agent.qgis_tools.web.response import (
    failure_of as _failure_of,
)
from ai_agent.qgis_tools.web.response import (
    integer as _integer,
)
from ai_agent.qgis_tools.web.response import (
    redirect_of,
)
from ai_agent.qgis_tools.web.url_policy import (
    MAX_URL_CHARS,
    address_sort_key,
    canonical_host,
    has_secret_query,
    is_public_address,
    netloc,
    origin,
    require_allowed_host_syntax,
    safe_url_label,
    unsafe_text_control,
)

MAX_BODY_BYTES = 2_000_000
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


class _AddressFailure(RuntimeError):
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
    manager = QgsNetworkAccessManager.instance()
    attempts = addresses[:1] if request_uses_proxy(manager, current) else addresses
    failure: _AddressFailure | None = None
    for address in attempts:
        try:
            return _download_document(
                current,
                extra_headers or {},
                approved_origin=approved_origin,
                address=address,
                epoch=request_epoch,
            )
        except _AddressFailure as error:
            failure = error
            guard_not_cancelled(request_epoch)
    raise ValueError(str(failure or FETCH_FAILED.format(url=safe_url_label(current), reason="service unavailable")))


def _download_document(
    current: str,
    headers: dict[str, str],
    *,
    approved_origin: tuple[str, str, int],
    address: str,
    epoch: int,
) -> tuple[str, str]:
    for redirect_count in range(MAX_REDIRECTS + 1):
        guard_not_cancelled(epoch)
        hop = _download_once(current, headers, address=address, epoch=epoch)
        guard_not_cancelled(epoch)
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
            failure = FETCH_FAILED.format(url=safe_url_label(current), reason=hop.error)
            if hop.status == 0:
                raise _AddressFailure(failure)
            raise ValueError(failure)
        if hop.status == 0:
            raise _AddressFailure(FETCH_FAILED.format(url=safe_url_label(current), reason="service unavailable"))
        guard_not_cancelled(epoch)
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
    manager = QgsNetworkAccessManager.instance()
    request = _network_request(url, headers, address=address, manager=manager)
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
            raise _AddressFailure(FETCH_FAILED.format(url=safe_url_label(url), reason="timed out"))
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


def _require_public_host(host: str, port: int, *, epoch: int | None = None) -> tuple[str, ...]:
    request_epoch = cancellation_epoch() if epoch is None else epoch
    guard_not_cancelled(request_epoch)
    normalized = (host or "").strip().lower().rstrip(".")
    addresses = _resolved_addresses(normalized, epoch=request_epoch)
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


def _resolved_addresses(host: str, *, epoch: int | None = None) -> tuple[str, ...]:
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


def _redirect_of(reply: Any) -> str:
    return redirect_of(reply, MAX_LOCATION_BYTES)


def _status_of(reply: Any) -> int:
    try:
        return _integer(reply.attribute(STATUS_ATTRIBUTE))
    except Exception:
        return 0
