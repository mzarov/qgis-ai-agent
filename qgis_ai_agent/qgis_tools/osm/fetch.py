from typing import Any

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis_ai_agent.qgis_tools.osm.overpass import endpoint

CONTENT_TYPE = "application/x-www-form-urlencoded"
USER_AGENT = "QGIS AI Agent"
EMPTY_MARKERS = ("<osm", "</osm>")
MAX_BYTES = 80 * 1024 * 1024
TOO_BIG = (
    "Overpass returned {megabytes:.0f} MB, which is over the limit of {limit} MB. "
    "Narrow the territory down or make value more specific, otherwise QGIS will choke on it."
)


def fetch(query: str) -> str:
    request = QNetworkRequest(QUrl(endpoint()))
    request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, CONTENT_TYPE)
    request.setRawHeader(b"User-Agent", USER_AGENT.encode("utf-8"))

    caller = QgsBlockingNetworkRequest()
    code = caller.post(request, QByteArray(f"data={query}".encode("utf-8")))
    if code != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise ValueError(_failure(caller))

    payload = bytes(caller.reply().content())
    _check_size(payload)
    text = payload.decode("utf-8", errors="replace")
    _check_shape(text)
    return text


def _check_size(payload: bytes) -> None:
    if len(payload) <= MAX_BYTES:
        return
    raise ValueError(
        TOO_BIG.format(megabytes=len(payload) / 1024 / 1024, limit=MAX_BYTES // 1024 // 1024)
    )


def _check_shape(text: str) -> None:
    if all(marker in text for marker in EMPTY_MARKERS):
        return
    head = text.strip()[:200]
    raise ValueError(
        f"Overpass returned something that is not OSM data: {head}. "
        "That usually means a broken query or an overloaded service."
    )


def _failure(caller: Any) -> str:
    try:
        message = caller.errorMessage()
    except Exception:
        message = ""
    return (
        f"Could not fetch data from Overpass: {message or 'the service is unavailable'}. "
        "The service is public and often busy — retry later or narrow the query down."
    )
