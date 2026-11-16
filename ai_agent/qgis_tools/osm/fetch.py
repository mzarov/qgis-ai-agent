import html
import re
from typing import Any
from urllib.parse import urlencode, urlsplit

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ai_agent.qgis_tools.common.background import download_progress
from ai_agent.qgis_tools.common.network import send

CONTENT_TYPE = "application/x-www-form-urlencoded"
USER_AGENT = "AI Agent"
EMPTY_MARKERS = ("<osm", "</osm>")
MAX_BYTES = 80 * 1024 * 1024
TOO_BIG = (
    "Overpass returned {megabytes:.0f} MB, which is over the limit of {limit} MB. "
    "Narrow the territory down or make value more specific, otherwise QGIS will choke on it."
)
# Overpass answers 200 even when a query breaks off: a remark marks the data incomplete.
REMARK = re.compile(r"<remark>(.*?)</remark>", re.DOTALL)
MAX_REMARK_CHARS = 300
# A server that could not take the query, as opposed to a query it could not run.
BUSY_MARKERS = ("too busy", "timed out", "timeout", "rate_limited", "load too high")
BUSY_STATUS = 429
CLIENT_ERROR = 400
SERVER_ERROR = 500
REFUSAL = re.compile(r"<strong[^>]*>\s*Error\s*</strong>\s*:\s*(.*?)</p>", re.DOTALL | re.IGNORECASE)
LOG_TAG = "AI Agent"
MIRROR_FAILED_TOO = "The mirror {host} was tried as well and did not answer either."
REFUSED = "Overpass refused the query: {said} Fix the query; sending it again unchanged will not help."
BROKEN_OFF = (
    "Overpass broke the query off and returned only part of the data, so nothing was loaded. It said: {remark} "
    "Narrow the territory down or make the query lighter; if the service is busy, retry later."
)


class Unanswered(ValueError):
    pass


def fetch_anywhere(query: str, urls: tuple[str, ...], feedback: Any = None) -> str:
    failures: list[Unanswered] = []
    for url in urls:
        try:
            return fetch(query, url, feedback)
        except Unanswered as failure:
            failures.append(failure)
            if _cancelled(feedback):
                break
            QgsMessageLog.logMessage(f"Overpass at {_host(url)} did not answer.", LOG_TAG, Qgis.MessageLevel.Warning)
    if len(failures) > 1:
        raise ValueError(f"{failures[0]} {MIRROR_FAILED_TOO.format(host=_host(urls[-1]))}")
    raise failures[0]


def fetch(query: str, url: str, feedback: Any = None) -> str:
    # Safe off the main thread: the address comes from the caller, nothing here reads the settings.
    request = QNetworkRequest(QUrl(url))
    request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, CONTENT_TYPE)
    request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))

    progress = download_progress(feedback) if feedback is not None else None
    answer = send(request, urlencode({"data": query}).encode("ascii"), feedback, progress)
    if answer.failed:
        raise _transport_failure(answer)

    payload = answer.body
    _check_size(payload)
    text = payload.decode("utf-8", errors="replace")
    _check_shape(text)
    _check_remark(text)
    return text


def _transport_failure(answer: Any) -> ValueError:
    refused = CLIENT_ERROR <= answer.status < SERVER_ERROR and answer.status != BUSY_STATUS
    said = _refusal(answer.body) if refused else ""
    if said:
        return ValueError(REFUSED.format(said=said))
    failure = ValueError if refused or answer.cancelled else Unanswered
    return failure(_failure(answer.error))


def _refusal(body: bytes) -> str:
    found = REFUSAL.findall(body.decode("utf-8", errors="replace"))
    return " ".join(" ".join(html.unescape(item).split()) for item in found)[:MAX_REMARK_CHARS]


def _busy(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BUSY_MARKERS)


def _cancelled(feedback: Any) -> bool:
    return feedback is not None and bool(feedback.isCanceled())


def _host(url: str) -> str:
    return urlsplit(url).hostname or url


def _check_size(payload: bytes) -> None:
    if len(payload) <= MAX_BYTES:
        return
    raise ValueError(TOO_BIG.format(megabytes=len(payload) / 1024 / 1024, limit=MAX_BYTES // 1024 // 1024))


def _check_shape(text: str) -> None:
    if all(marker in text for marker in EMPTY_MARKERS):
        return
    head = text.strip()[:200]
    failure = Unanswered if _busy(text) else ValueError
    raise failure(
        f"Overpass returned something that is not OSM data: {head}. "
        "That usually means a broken query or an overloaded service."
    )


def _check_remark(text: str) -> None:
    found = REMARK.search(text)
    if found is None:
        return
    remark = " ".join(html.unescape(found.group(1)).split())[:MAX_REMARK_CHARS]
    failure = Unanswered if _busy(remark) else ValueError
    raise failure(BROKEN_OFF.format(remark=remark))


def _failure(message: str) -> str:
    return (
        f"Could not fetch data from Overpass: {message or 'the service is unavailable'}. "
        "The service is public and often busy — retry later or narrow the query down."
    )
