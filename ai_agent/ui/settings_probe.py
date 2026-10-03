"""The connection test of the settings window: start, cancel, report, and close only once it stopped.

A mixin of `SettingsDialog`: it reads the dialog's fields through `_overrides`
and reports into its status card and test button.
"""

import time
from typing import Any

from ai_agent.core.llm.probe_worker import ProbeThread
from ai_agent.core.settings import reset_capabilities
from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.connection_widgets import STATE_BAD, STATE_IDLE, STATE_OK
from ai_agent.ui.durations import format_seconds

NOT_TESTED_DETAIL = tr("Not tested yet.")
CONNECTED = tr("Connected · {0} · {1}")
FAILED = tr("The connection failed")
PROBE_STOP_MS = 3000
TESTING = tr("Testing the connection…")
CANCELLING = tr("Cancelling the connection test…")
CANCELLED = tr("Connection test cancelled.")
MODEL_REQUIRED = tr("Enter a model name from the provider.")


class ConnectionProbeMixin:
    _probe_thread: ProbeThread | None
    _probe_was_cancelled: bool
    _reject_after_probe: bool
    _probe_started: float
    model_edit: Any
    test_btn: Any
    status_card: Any

    def _stop_probe_now(self) -> None:
        thread = self._probe_thread
        if thread is not None and thread.isRunning():
            thread.cancel()
            thread.wait(PROBE_STOP_MS)

    def _test_connection(self) -> None:
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._cancel_probe()
            return
        if not self.model_edit.text().strip():
            self._show(MODEL_REQUIRED, style.danger(self.palette()))
            return
        if not self._valid_url(self._edited_url()):
            return
        self.test_btn.setText(tr("Cancel test"))
        self.status_card.show_state(STATE_IDLE, TESTING, "")
        self._probe_started = time.monotonic()
        self._probe_was_cancelled = False
        thread = ProbeThread(self._overrides(), self)
        thread.completed.connect(self._on_probe_completed)
        thread.finished.connect(lambda: self._on_probe_finished(thread))
        self._probe_thread = thread
        thread.start()

    def _on_probe_completed(self, ok: bool, message: str) -> None:
        if not ok:
            self.status_card.show_state(STATE_BAD, FAILED, message)
            return
        overrides = self._overrides()
        reset_capabilities(
            overrides["url_override"], overrides.get("model_override") or "", overrides.get("dialect_override")
        )
        seconds = time.monotonic() - self._probe_started
        summary = CONNECTED.format(self.model_edit.text().strip(), format_seconds(seconds))
        self.status_card.show_state(STATE_OK, summary, message)

    def _show_untested(self) -> None:
        self.status_card.show_state(STATE_IDLE, NOT_TESTED_DETAIL, "")

    def _on_probe_finished(self, thread: ProbeThread) -> None:
        thread.deleteLater()
        if self._probe_thread is not thread:
            return
        cancelled = self._probe_was_cancelled
        close_dialog = self._reject_after_probe
        self._probe_thread = None
        self._probe_was_cancelled = False
        self._reject_after_probe = False
        self.test_btn.setEnabled(True)
        self.test_btn.setText(tr("Test connection"))
        if close_dialog:
            super().reject()
        elif cancelled:
            self.status_card.show_state(STATE_IDLE, CANCELLED, "")

    def _cancel_probe(self) -> None:
        thread = self._probe_thread
        if thread is None or not thread.isRunning():
            return
        self._probe_was_cancelled = True
        thread.cancel()
        self.test_btn.setEnabled(False)
        self.status_card.show_state(STATE_IDLE, CANCELLING, "")

    def reject(self) -> None:
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._reject_after_probe = True
            self._cancel_probe()
            return
        self._cancel_probe()
        super().reject()
