import time
from typing import Any

from qgis.PyQt.QtWidgets import QDialog

from ai_agent.core.llm.probe_worker import ProbeThread
from ai_agent.core.settings import reset_capabilities, set_detected_context_window, set_supports_images
from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.connection_widgets import STATE_BAD, STATE_IDLE, STATE_OK
from ai_agent.ui.durations import format_seconds
from ai_agent.ui.settings_layout import CONNECTION

NOT_TESTED_DETAIL = tr("Not tested yet.")
CONNECTED = tr("Connected · {0} · {1}")
FAILED = tr("The connection failed")
TESTING = tr("Testing the connection…")
CANCELLING = tr("Cancelling the connection test…")
CANCELLED = tr("Connection test cancelled.")
MODEL_REQUIRED = tr("Enter a model name from the provider.")
TEXT_ONLY = tr("This model does not see pictures: the agent checks the map by reading the data instead.")
SAVE = tr("Save")
SAVE_ANYWAY = tr("Save anyway")


class ConnectionProbeMixin:
    _probe_thread: ProbeThread | None
    _probe_was_cancelled: bool
    _close_after_probe: "QDialog.DialogCode | None"
    _probe_started: float
    model_edit: Any
    test_btn: Any
    status_card: Any
    _probe_scope: tuple[str, str, str | None]
    _probe_report: tuple[str, str]
    _probed: tuple[Any, ...] | None
    _tested: set[tuple[Any, ...]]
    _refused: tuple[Any, ...] | None
    _save_waits: bool
    save_btn: Any

    def _test_connection(self) -> None:
        if self._probe_running():
            self._cancel_probe()
            return
        if not self.model_edit.text().strip():
            self._show(MODEL_REQUIRED, style.danger(self.palette()))
            return
        if self._valid_url(self._edited_url()):
            self._start_probe()

    def _connection(self) -> tuple[Any, ...]:
        return tuple(self._overrides().values())

    def _probe_before_save(self) -> bool:
        wanted = self._connection()
        if wanted in self._tested or wanted == self._refused:
            return False
        if not self._probe_running():
            self._start_probe()
        elif self._probed != wanted:
            # The save tries again once that test's thread is gone.
            self._cancel_probe()
        self._save_waits = True
        self.save_btn.setEnabled(False)
        self._show(TESTING, style.muted(self.palette()))
        return True

    def _forget_refusal(self, *_args: Any) -> None:
        if self._refused is not None:
            self._refused = None
            self.save_btn.setText(SAVE)

    def _start_probe(self) -> None:
        self.test_btn.setText(tr("Cancel test"))
        self.status_card.show_state(STATE_IDLE, TESTING, "")
        self._probe_started = time.monotonic()
        self._probe_was_cancelled = False
        overrides = self._overrides()
        self._probed = tuple(overrides.values())
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
            self._refuse_probed()
            return
        self._tested.add(self._probed)
        self._forget_refusal()
        reset_capabilities(*self._probe_scope)
        seconds = time.monotonic() - self._probe_started
        summary = CONNECTED.format(self.model_edit.text().strip(), format_seconds(seconds))
        self._probe_report = (summary, message)
        self.status_card.show_state(STATE_OK, summary, message)

    def _refuse_probed(self) -> None:
        # Only what is still in the fields: an edit made during the test is another connection.
        if self._probed not in self._tested and self._probed == self._connection():
            self._refused = self._probed
            self.save_btn.setText(SAVE_ANYWAY)
        if self._save_waits:
            self._end_waiting_save()
            self._show(FAILED, style.danger(self.palette()))
            self.show_page(CONNECTION)

    def _end_waiting_save(self) -> None:
        self._save_waits = False
        self.save_btn.setEnabled(True)
        self._show("", style.muted(self.palette()))

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
        waiting = self._save_waits
        self._probe_thread = None
        self._probe_was_cancelled = False
        self.test_btn.setEnabled(True)
        self.test_btn.setText(tr("Test connection"))
        if cancelled:
            self.status_card.show_state(STATE_IDLE, CANCELLED, "")
        if self._close_if_waiting() or not waiting:
            return
        self._end_waiting_save()
        self._save()

    def _probe_running(self) -> bool:
        return self._probe_thread is not None and self._probe_thread.isRunning()

    def _cancel_probe(self) -> None:
        if not self._probe_running():
            return
        if self._save_waits:
            self._end_waiting_save()
        self._probe_was_cancelled = True
        self._probe_thread.cancel()
        self.test_btn.setEnabled(False)
        self.status_card.show_state(STATE_IDLE, CANCELLING, "")

    def accept(self) -> None:
        self._close_once_stopped(QDialog.DialogCode.Accepted)

    def reject(self) -> None:
        if self._close_after_probe != QDialog.DialogCode.Accepted:
            self._close_once_stopped(QDialog.DialogCode.Rejected)

    def _close_once_stopped(self, result: QDialog.DialogCode) -> None:
        # The window owns its threads: deleting it while one of them runs aborts QGIS.
        if self._probe_running() or self._list_running():
            self._close_after_probe = result
            self._cancel_probe()
            self._cancel_listing()
            return
        self.done(result)

    def _close_if_waiting(self) -> bool:
        result = self._close_after_probe
        if result is None or self._probe_running() or self._list_running():
            return result is not None
        self._close_after_probe = None
        self.done(result)
        return True
