"""Opt-in usage counts: once a day, how much the agent was used — never what for.

Off until the user says yes, on the card after a first answer or in Settings →
Privacy; without a yes nothing is even counted. What is counted: runs, applied
batches, the names of the tools and skills used, the kinds of failures, and the
versions around them (plugin, QGIS, the OS family, the interface language, a
local or remote model and its API format). Never a request, an answer, a layer,
a value or a place. A random id, kept in the QGIS settings, tells one install
from another; the collector stores only its hash.

The counts of a day go out once that day is over, in one small request on the
QGIS network stack, to the collector in `telemetry/worker`. A failed send keeps
them for the next try. The collector's aggregates are public: see the usage
statistics page of the documentation.
"""

import datetime
import json
import re
import sys
import uuid
from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from ai_agent.core.about import plugin_version
from ai_agent.core.llm.client import is_local
from ai_agent.core.settings import get_api_url, get_dialect
from ai_agent.i18n import locale_code

# Set once the collector is deployed; empty keeps the whole feature off, the card included.
COLLECTOR_URL = ""
PING_PATH = "/v1/ping"
PAYLOAD_VERSION = 1
PREFIX = "ai_agent/usage"
CONSENT_KEY = f"{PREFIX}/consent"
INSTALL_KEY = f"{PREFIX}/install"
DAY_KEY = f"{PREFIX}/day"
COUNTS_KEY = f"{PREFIX}/counts"
PENDING_KEY = f"{PREFIX}/pending"
CONSENT_YES = "yes"
CONSENT_NO = "no"
NAME = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
MAX_NAMES = 150
MAX_COUNT = 100_000
VERSION_CHARS = 32
LOG_TAG = "AI Agent"
OS_FAMILIES = (("darwin", "macos"), ("win", "windows"), ("linux", "linux"))
DIALECTS = ("openai", "anthropic")
OK_STATUSES = (200, 204)
# The collector takes a day at most this far from its own date; an older pending day is dropped, not retried.
MAX_DAY_AGE = 2
REFUSED = 400


def collector_url() -> str:
    return COLLECTOR_URL.rstrip("/")


def consent() -> str:
    """'yes', 'no', or '' while the user was never asked."""
    value = QgsSettings().value(CONSENT_KEY, "", type=str)
    return value if value in (CONSENT_YES, CONSENT_NO) else ""


def set_consent(agreed: bool) -> None:
    settings = QgsSettings()
    settings.setValue(CONSENT_KEY, CONSENT_YES if agreed else CONSENT_NO)
    if not agreed:
        # A no takes back what was counted under an earlier yes.
        for key in (COUNTS_KEY, DAY_KEY, PENDING_KEY):
            settings.remove(key)


def save_usage_choice(checked: bool) -> None:
    """The Privacy switch saved: a yes or a no, but an untouched switch of someone never asked stays unasked."""
    if checked or consent() == CONSENT_YES:
        set_consent(checked)


def should_ask() -> bool:
    return bool(collector_url()) and consent() == ""


def enabled() -> bool:
    return bool(collector_url()) and consent() == CONSENT_YES


def empty_counts() -> dict[str, Any]:
    return {"runs": 0, "applies": 0, "failures": {}, "tools": {}, "skills": {}}


def add(counts: dict[str, Any], kind: str, name: str = "") -> dict[str, Any]:
    """`counts` with one more `kind` (runs, applies) or one more `name` under failures, tools or skills."""
    if kind in ("runs", "applies"):
        counts[kind] = min(MAX_COUNT, int(counts.get(kind, 0)) + 1)
        return counts
    key = str(name or "").strip().lower()
    group = counts.setdefault(kind, {})
    if not NAME.match(key) or (key not in group and len(group) >= MAX_NAMES):
        return counts
    group[key] = min(MAX_COUNT, int(group.get(key, 0)) + 1)
    return counts


def payload(install: str, day: str, counts: dict[str, Any]) -> dict[str, Any]:
    """The day's ping, exactly the fields the collector accepts."""
    url = get_api_url()
    dialect = get_dialect()
    return {
        "v": PAYLOAD_VERSION,
        "install": install,
        "day": day,
        "plugin": _version(plugin_version()),
        "qgis": _version(str(Qgis.version()).split("-")[0]),
        "os": os_family(sys.platform),
        "locale": re.sub(r"[^A-Za-z_-]", "", locale_code())[:16] or "en",
        "provider": "local" if url and is_local(url) else "remote",
        "dialect": dialect if dialect in DIALECTS else "openai",
        "runs": int(counts.get("runs", 0)),
        "applies": int(counts.get("applies", 0)),
        "failures": dict(counts.get("failures") or {}),
        "tools": dict(counts.get("tools") or {}),
        "skills": dict(counts.get("skills") or {}),
    }


def os_family(platform: str) -> str:
    return next((family for prefix, family in OS_FAMILIES if platform.startswith(prefix)), "other")


def has_counts(counts: dict[str, Any]) -> bool:
    return bool(counts.get("runs") or counts.get("applies") or counts.get("tools"))


def _version(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._+-]", "", text)[:VERSION_CHARS] or "unknown"


class UsageStats:
    """The day's counts in the QGIS settings; a day that is over waits as pending until it is sent."""

    def __init__(self, today: Any = None) -> None:
        self._today = today or (lambda: datetime.date.today().isoformat())
        self._reply: Any = None

    def note(self, kind: str, name: str = "") -> None:
        if not enabled():
            return
        self._roll_over()
        settings = QgsSettings()
        counts = _loaded(settings.value(COUNTS_KEY, "", type=str))
        settings.setValue(COUNTS_KEY, json.dumps(add(counts, kind, name)))
        settings.setValue(DAY_KEY, self._today())

    def flush(self) -> None:
        """Send a day that is over; nothing while one send is still on its way."""
        if not enabled() or self._reply is not None:
            return
        self._roll_over()
        pending = _loaded(QgsSettings().value(PENDING_KEY, "", type=str))
        day, counts = str(pending.get("day") or ""), pending.get("counts") or {}
        if not day or not has_counts(counts) or _too_old(day, self._today()):
            QgsSettings().remove(PENDING_KEY)
            return
        body = json.dumps(payload(self._install(), day, counts)).encode("utf-8")
        request = QNetworkRequest(QUrl(collector_url() + PING_PATH))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        self._reply = QgsNetworkAccessManager.instance().post(request, QByteArray(body))
        self._reply.finished.connect(self._sent)

    def _roll_over(self) -> None:
        """Counts of an earlier day become the pending ping; a newer pending day replaces an older one."""
        settings = QgsSettings()
        day = settings.value(DAY_KEY, "", type=str) or ""
        if not day or day >= self._today():
            return
        counts = _loaded(settings.value(COUNTS_KEY, "", type=str))
        if has_counts(counts):
            settings.setValue(PENDING_KEY, json.dumps({"day": day, "counts": counts}))
        settings.remove(COUNTS_KEY)
        settings.remove(DAY_KEY)

    def _sent(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if reply.error() == QNetworkReply.NetworkError.NoError and status in OK_STATUSES:
            QgsSettings().remove(PENDING_KEY)
        elif status == REFUSED:
            # Refused as malformed: sending the same counts again would be refused again.
            QgsSettings().remove(PENDING_KEY)
        else:
            QgsMessageLog.logMessage(
                f"Usage counts were not sent ({reply.errorString()}); they wait for the next try.",
                LOG_TAG,
                Qgis.MessageLevel.Info,
            )
        reply.deleteLater()

    @staticmethod
    def _install() -> str:
        settings = QgsSettings()
        install = settings.value(INSTALL_KEY, "", type=str)
        if not install:
            install = str(uuid.uuid4())
            settings.setValue(INSTALL_KEY, install)
        return install


def _too_old(day: str, today: str) -> bool:
    try:
        age = datetime.date.fromisoformat(today) - datetime.date.fromisoformat(day)
    except ValueError:
        return True
    return age.days > MAX_DAY_AGE


def _loaded(text: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
