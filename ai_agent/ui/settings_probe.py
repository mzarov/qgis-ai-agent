"""The connection test of the settings window: start, cancel, report, and close only once it stopped.

A mixin of `SettingsDialog`: it reads the dialog's fields through `_overrides`
and reports into its status card and test button.
"""

import time
from typing import Any

from qgis.PyQt.QtWidgets import QDialog

from ai_agent.core.llm.probe_worker import ProbeThread
from ai_agent.core.settings import reset_capabilities, set_detected_context_window, set_supports_images
from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.connection_widgets import STATE_BAD, STATE_IDLE, STATE_OK
from ai_agent.ui.durations import format_seconds

NOT_TESTED_DETAIL = tr("Not tested yet.")
CONNECTED = tr("Connected · {0} · {1}")
FAILED = tr("The connection failed")
TESTING = tr("Testing the connection…")
CANCELLING = tr("Cancelling the connection test…")
CANCELLED = tr("Connection test cancelled.")
MODEL_REQUIRED = tr("Enter a model name from the provider.")
TEXT_ONLY = tr("This model does not see pictures: the agent checks the map by reading the data instead.")


class ConnectionProbeMixin:
    _probe_thread: ProbeThread | None
    _probe_was_cancelled: bool
    _close_after_probe: QDialog.DialogCode | None
    _probe_started: float
    model_edit: Any
    test_btn: Any
    status_card: Any
    _probe_scope: tuple[str, str, str | None]
    _probe_report: tuple[str, str]

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
        overrides = self._overrides()
        # The window is stored for what was tested, even if the fields change meanwhile.
        self._probe_scope = (
            overrides["url_override"],
            overrides.get("model_override") or "",
            overrides.get("dialect_override"),
        )
        thread = ProbeThread(overrides, self)
        thread.completed.connect(self._on_probe_completed)
        thread.window_found.connect(self._on_window_found)
        thread.images_checked.connect(self._on_images_checked)
        thread.finished.connect(lambda: self._on_probe_finished(thread))
        self._probe_thread = thread
        thread.start()

    def _on_probe_completed(self, ok: bool, message: str) -> None:
        if not ok:
            self.status_card.show_state(STATE_BAD, FAILED, message)
            return
        reset_capabilities(*self._probe_scope)
        seconds = time.monotonic() - self._probe_started
        summary = CONNECTED.format(self.model_edit.text().strip(), format_seconds(seconds))
        self._probe_report = (summary, message)
        self.status_card.show_state(STATE_OK, summary, message)

    def _on_window_found(self, tokens: int) -> None:
        url, model, dialect = self._probe_scope
        set_detected_context_window(tokens, url, model, dialect)

    def _on_images_checked(self, sees: bool) -> None:
        url, model, dialect = self._probe_scope
        set_supports_images(url, sees, model, dialect)
        if not sees:
            summary, message = self._probe_report
            self.status_card.show_state(STATE_OK, summary, f"{message}\n{TEXT_ONLY}")

    def _show_untested(self) -> None:
        self.status_card.show_state(STATE_IDLE, NOT_TESTED_DETAIL, "")

    def _on_probe_finished(self, thread: ProbeThread) -> None:
        thread.deleteLater()
        if self._probe_thread is not thread:
            return
        cancelled = self._probe_was_cancelled
        close_with = self._close_after_probe
        self._probe_thread = None
        self._probe_was_cancelled = False
        self._close_after_probe = None
        self.test_btn.setEnabled(True)
        self.test_btn.setText(tr("Test connection"))
        if close_with is not None:
            self.done(close_with)
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

    def accept(self) -> None:
        self._close_once_stopped(QDialog.DialogCode.Accepted)

    def reject(self) -> None:
        # A Save waiting for the test has stored everything already: a Cancel now cannot take that back.
        if self._close_after_probe != QDialog.DialogCode.Accepted:
            self._close_once_stopped(QDialog.DialogCode.Rejected)

    def _close_once_stopped(self, result: QDialog.DialogCode) -> None:
        """Close now, or once the running test has stopped.

        The window owns the test's thread: deleting the window while that thread runs aborts QGIS.
        """
        if self._probe_thread is not None and self._probe_thread.isRunning():
            self._close_after_probe = result
            self._cancel_probe()
            return
        self.done(result)
