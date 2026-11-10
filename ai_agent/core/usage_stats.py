import datetime
import json
import time
import uuid
from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtCore import QByteArray, QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from ai_agent.core.about import plugin_version
from ai_agent.core.usage_payload import (
    CONVERSATIONS,
    COUNTED_MODES,
    REQUEST_BUCKETS,
    REQUESTS,
    SECOND_BUCKETS,
    STEP_BUCKETS,
    TOKEN_BUCKETS,
    add,
    bucket,
    has_counts,
    payload,
    version_text,
)

COLLECTOR_URL = "https://ai-agent-usage.mzarov.workers.dev"
PING_PATH = "/v1/ping"
PREFIX = "ai_agent/usage"
CONSENT_KEY = f"{PREFIX}/consent"
INSTALL_KEY = f"{PREFIX}/install"
DAY_KEY = f"{PREFIX}/day"
COUNTS_KEY = f"{PREFIX}/counts"
PENDING_KEY = f"{PREFIX}/pending"
NOTICE_KEY = f"{PREFIX}/noticed"
TASKS_KEY = f"{PREFIX}/tasks"
CONSENT_YES = "yes"
CONSENT_NO = "no"
LOG_TAG = "AI Agent"
OK_STATUSES = (200, 204)
MAX_DAY_AGE = 7
MAX_PENDING_DAYS = 3
CLIENT_ERRORS = range(400, 500)
RATE_LIMITED = 429
TODAY_DELAY_MS = 60_000
MAX_TASKS = 50


def collector_url() -> str:
    return COLLECTOR_URL.rstrip("/")


def consent() -> str:
    value = QgsSettings().value(CONSENT_KEY, "", type=str)
    return value if value in (CONSENT_YES, CONSENT_NO) else ""


def set_consent(agreed: bool) -> None:
    settings = QgsSettings()
    settings.setValue(CONSENT_KEY, CONSENT_YES if agreed else CONSENT_NO)
    if not agreed:
        for key in (COUNTS_KEY, DAY_KEY, PENDING_KEY, TASKS_KEY):
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


class UsageStats:
    def __init__(self, today: Any = None, clock: Any = time.monotonic) -> None:
        self._today = today or (lambda: datetime.date.today().isoformat())
        self._clock = clock
        # Read once: a plugin installed later into the same folder would lend its version to this one.
        self._plugin = version_text(plugin_version())
        self._run_open = False
        self._busy_since: float | None = None
        self._active = 0.0
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

    def run_started(self, kind: str, conversation: str = "", mode: str = "") -> None:
        self.note(kind)
        if kind == REQUESTS and conversation:
            self.note(CONVERSATIONS, f"c{conversation}")
            self._count_task(conversation)
        if mode in COUNTED_MODES:
            self.note("modes", mode)
        self._run_open = True
        self._active = 0.0
        self._busy_since = self._clock()

    def note_busy(self, busy: bool) -> None:
        if busy and self._busy_since is None:
            self._busy_since = self._clock()
        elif not busy and self._busy_since is not None:
            self._active += self._clock() - self._busy_since
            self._busy_since = None

    def run_ended(self, outcome: str, spent: Any) -> None:
        if not self._run_open:
            return
        self.note_busy(False)
        self._run_open = False
        spent = spent if isinstance(spent, dict) else {}
        tokens = int(spent.get("prompt_tokens", 0)) + int(spent.get("completion_tokens", 0))
        self.note("outcomes", outcome)
        self.note("steps", bucket(int(spent.get("requests", 0)), STEP_BUCKETS))
        self.note("durations", bucket(self._active, SECOND_BUCKETS))
        self.note("tokens", bucket(tokens, TOKEN_BUCKETS))

    def note_apply(self, conversation: str) -> None:
        self.note("applies")
        if not enabled():
            return
        tasks = _loaded(QgsSettings().value(TASKS_KEY, "", type=str))
        pending = int(tasks.get(conversation, 0) or 0)
        # A later stage of the same request is not a new result.
        if pending > 0:
            self.note("to_apply", bucket(pending, REQUEST_BUCKETS))
            tasks[conversation] = 0
            _keep_tasks(tasks)

    def _count_task(self, conversation: str) -> None:
        if not enabled():
            return
        tasks = _loaded(QgsSettings().value(TASKS_KEY, "", type=str))
        pending = int(tasks.pop(conversation, 0) or 0)
        tasks[conversation] = pending + 1
        _keep_tasks(tasks)

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
        body = json.dumps(payload(self._install(), day, counts, self._plugin)).encode("utf-8")
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
        install = str(settings.value(INSTALL_KEY, "", type=str) or "")
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


def _keep_tasks(tasks: dict[str, Any]) -> None:
    QgsSettings().setValue(TASKS_KEY, json.dumps(dict(list(tasks.items())[-MAX_TASKS:])))


def _loaded(text: Any) -> dict[str, Any]:
    value = _decoded(text)
    return value if isinstance(value, dict) else {}


def _decoded(text: Any) -> Any:
    try:
        return json.loads(str(text or "") or "{}")
    except ValueError:
        return {}
