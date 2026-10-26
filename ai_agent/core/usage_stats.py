import datetime
import json
import re
import sys
import uuid
from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtCore import QByteArray, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from ai_agent.core.about import plugin_version
from ai_agent.core.llm.client import is_local
from ai_agent.core.settings import get_api_url, get_dialect, has_saved_model
from ai_agent.i18n import locale_code

COLLECTOR_URL = "https://ai-agent-usage.mzarov.workers.dev"
PING_PATH = "/v1/ping"
PAYLOAD_VERSION = 2
PREFIX = "ai_agent/usage"
CONSENT_KEY = f"{PREFIX}/consent"
INSTALL_KEY = f"{PREFIX}/install"
DAY_KEY = f"{PREFIX}/day"
COUNTS_KEY = f"{PREFIX}/counts"
PENDING_KEY = f"{PREFIX}/pending"
NOTICE_KEY = f"{PREFIX}/noticed"
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
MAX_DAY_AGE = 7
MAX_PENDING_DAYS = 3
CLIENT_ERRORS = range(400, 500)
RATE_LIMITED = 429
ACTIVE = "active"
TODAY_DELAY_MS = 60_000


def collector_url() -> str:
    return COLLECTOR_URL.rstrip("/")


def consent() -> str:
    value = QgsSettings().value(CONSENT_KEY, "", type=str)
    return value if value in (CONSENT_YES, CONSENT_NO) else ""


def set_consent(agreed: bool) -> None:
    settings = QgsSettings()
    settings.setValue(CONSENT_KEY, CONSENT_YES if agreed else CONSENT_NO)
    if not agreed:
        for key in (COUNTS_KEY, DAY_KEY, PENDING_KEY):
            settings.remove(key)


def noticed() -> bool:
    return bool(QgsSettings().value(NOTICE_KEY, False, type=bool))


def mark_noticed() -> None:
    QgsSettings().setValue(NOTICE_KEY, True)


def should_notify() -> bool:
    return bool(collector_url()) and consent() == "" and not noticed()


def enabled() -> bool:
    choice = consent()
    return bool(collector_url()) and choice != CONSENT_NO and (choice == CONSENT_YES or noticed())


def add(counts: dict[str, Any], kind: str, name: str = "") -> dict[str, Any]:
    if kind == ACTIVE:
        counts[ACTIVE] = True
        return counts
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
        "configured": has_saved_model(),
        "runs": int(counts.get("runs", 0)),
        "applies": int(counts.get("applies", 0)),
        "failures": dict(counts.get("failures") or {}),
        "tools": dict(counts.get("tools") or {}),
        "tool_errors": dict(counts.get("tool_errors") or {}),
        "skills": dict(counts.get("skills") or {}),
    }


def os_family(platform: str) -> str:
    return next((family for prefix, family in OS_FAMILIES if platform.startswith(prefix)), "other")


def has_counts(counts: dict[str, Any]) -> bool:
    return bool(counts.get(ACTIVE) or counts.get("runs") or counts.get("applies") or counts.get("tools"))


def _version(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z._+-]", "", text)[:VERSION_CHARS] or "unknown"


class UsageStats:
    def __init__(self, today: Any = None) -> None:
        self._today = today or (lambda: datetime.date.today().isoformat())
        self._reply: Any = None
        self._sending = ""
        self._today_due = False
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(TODAY_DELAY_MS)
        self._timer.timeout.connect(self._send_today)

    def note(self, kind: str, name: str = "") -> None:
        if not enabled():
            return
        self._roll_over()
        settings = QgsSettings()
        counts = _loaded(settings.value(COUNTS_KEY, "", type=str))
        settings.setValue(COUNTS_KEY, json.dumps(add(counts, kind, name)))
        settings.setValue(DAY_KEY, self._today())
        # The delay leaves time to turn counting off after the first notice, before anything of today leaves.
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def flush(self) -> None:
        if not enabled() or self._reply is not None:
            return
        self._roll_over()
        today = self._today()
        days = [entry for entry in _pending_days() if has_counts(entry["counts"]) and not _too_old(entry["day"], today)]
        _keep_pending(days)
        if days:
            self._post(days[0]["day"], days[0]["counts"], finished=True)
        elif self._today_due:
            self._today_due = False
            settings = QgsSettings()
            counts = _loaded(settings.value(COUNTS_KEY, "", type=str))
            if has_counts(counts):
                # The collector keeps a day's latest ping, and the whole day goes out again once it is over.
                self._post(settings.value(DAY_KEY, "", type=str) or today, counts, finished=False)

    def _send_today(self) -> None:
        self._today_due = True
        self.flush()

    def _post(self, day: str, counts: dict[str, Any], finished: bool) -> None:
        self._sending = day if finished else ""
        body = json.dumps(payload(self._install(), day, counts)).encode("utf-8")
        request = QNetworkRequest(QUrl(collector_url() + PING_PATH))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        self._reply = QgsNetworkAccessManager.instance().post(request, QByteArray(body))
        self._reply.finished.connect(self._sent)

    def _roll_over(self) -> None:
        settings = QgsSettings()
        day = settings.value(DAY_KEY, "", type=str) or ""
        if not day or day >= self._today():
            return
        counts = _loaded(settings.value(COUNTS_KEY, "", type=str))
        if has_counts(counts):
            days = [entry for entry in _pending_days() if entry["day"] != day]
            _keep_pending([*days, {"day": day, "counts": counts}][-MAX_PENDING_DAYS:])
        settings.remove(COUNTS_KEY)
        settings.remove(DAY_KEY)

    def _sent(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        delivered = reply.error() == QNetworkReply.NetworkError.NoError and status in OK_STATUSES
        # Turned away (malformed, too large): the same counts would be turned away again.
        refused = status in CLIENT_ERRORS and status != RATE_LIMITED
        reply.deleteLater()
        if not (delivered or refused):
            QgsMessageLog.logMessage(
                f"Usage counts were not sent ({reply.errorString()}); they wait for the next try.",
                LOG_TAG,
                Qgis.MessageLevel.Info,
            )
            return
        if self._sending:
            _keep_pending([entry for entry in _pending_days() if entry["day"] != self._sending])
        self.flush()

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


def _pending_days() -> list[dict[str, Any]]:
    value = _decoded(QgsSettings().value(PENDING_KEY, "", type=str))
    # The previous version kept a single day as one object.
    entries = value if isinstance(value, list) else [value]
    return [
        {"day": entry["day"], "counts": entry["counts"]}
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("day"), str) and isinstance(entry.get("counts"), dict)
    ]


def _keep_pending(days: list[dict[str, Any]]) -> None:
    if days:
        QgsSettings().setValue(PENDING_KEY, json.dumps(days))
    else:
        QgsSettings().remove(PENDING_KEY)


def _loaded(text: Any) -> dict[str, Any]:
    value = _decoded(text)
    return value if isinstance(value, dict) else {}


def _decoded(text: Any) -> Any:
    try:
        return json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
