from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QPoint, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase, QIcon
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
from ai_agent.ui.composer import Composer
from ai_agent.ui.conversation import ConversationView
from ai_agent.ui.progress import ProgressLine

TITLE = "AI Agent"
NO_SESSIONS_LABEL = tr("No past conversations")
HEADER_MARGINS = (11, 8, 9, 8)
HEADER_ICON = 15
HEADER_BUTTON = 24
BODY_MARGINS = (9, 0, 9, 9)
BODY_NAME = "agentBody"
MENU_GAP = 4


class AgentDockWidget(QDockWidget):
    open_settings_clicked = pyqtSignal()
    new_session_clicked = pyqtSignal()
    session_chosen = pyqtSignal(str)
    prompt_submitted = pyqtSignal(str)
    stop_clicked = pyqtSignal()
    confirm_plan_clicked = pyqtSignal()
    cancel_plan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self._sessions_provider: Callable[[], list[tuple[str, str]]] = list
        body = QWidget()
        body.setObjectName(BODY_NAME)
        style.fill(body, style.background(self.palette()))
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self._build_conversation(), 1)
        column.addWidget(self._build_composer())
        self.setWidget(body)
        self.composer.set_popup_host(body)

    def _build_header(self) -> QWidget:
        header = QWidget()
        palette = self.palette()
        header.setStyleSheet(f"border-bottom: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};")
        row = QHBoxLayout(header)
        row.setContentsMargins(*HEADER_MARGINS)
        row.setSpacing(4)

        # No title here: the dock's own title bar already says AI Agent.
        self._usage_label = QLabel("")
        self._usage_label.setStyleSheet(f"border: none; color: {style.css_color(style.muted(palette))};")
        row.addWidget(self._usage_label, 1)
        self._sessions_button = self._build_action(icons.sessions, "⟲", tr("Conversations"), self._show_sessions)
        row.addWidget(self._sessions_button)
        row.addWidget(self._build_action(icons.clear, "+", tr("New conversation"), self.new_session_clicked.emit))
        row.addWidget(self._build_action(icons.settings, "⚙", tr("Settings"), self.open_settings_clicked.emit))
        return header

    def _build_action(
        self,
        paint: Callable[[Any, int], QIcon],
        glyph: str,
        tooltip: str,
        handler: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(HEADER_BUTTON, HEADER_BUTTON)
        button.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f"color: {style.css_color(style.muted(self.palette()))}; font-size: 14px; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(self.palette()))};"
            "border-radius: 5px; }"
        )
        icon = _drawn(paint, style.muted(self.palette()), HEADER_ICON)
        if icon is None:
            button.setText(glyph)
        else:
            button.setIcon(icon)
            button.setIconSize(QSize(HEADER_ICON, HEADER_ICON))
        button.clicked.connect(handler)
        return button

    def set_configured(self, configured: bool) -> None:
        self.conversation.set_configured(configured)
        self.composer.set_configured(configured)

    def set_model(self, name: str) -> None:
        self.composer.set_model(name)

    def _build_conversation(self) -> QWidget:
        self.conversation = ConversationView()
        self.conversation.confirm_requested.connect(self.confirm_plan_clicked.emit)
        self.conversation.cancel_requested.connect(self.cancel_plan_clicked.emit)
        self.conversation.suggestion_chosen.connect(self._on_suggestion)
        self.conversation.settings_requested.connect(self.open_settings_clicked.emit)
        return self.conversation

    def _build_composer(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(*BODY_MARGINS)
        self.progress = ProgressLine(self.palette())
        layout.addWidget(self.progress)
        self.composer = Composer()
        self.composer.submitted.connect(self.prompt_submitted.emit)
        self.composer.stopped.connect(self.stop_clicked.emit)
        layout.addWidget(self.composer)
        return holder

    def set_session_source(self, provider: Callable[[], list[tuple[str, str]]]) -> None:
        self._sessions_provider = provider

    def set_skill_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self.composer.set_skill_source(provider)

    def set_layer_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self.composer.set_layer_source(provider)

    def focus_prompt(self) -> None:
        self.composer.focus()

    def restore_prompt(self, text: str) -> None:
        self.composer.restore(text)

    def keep_stream(self) -> str:
        return self.conversation.keep_draft()

    def _on_suggestion(self, text: str) -> None:
        self.prompt_submitted.emit(text)
        self.composer.focus()

    def _show_sessions(self) -> None:
        # Past conversations only: starting a new one is the button right next to this one.
        menu = controls.menu(self, self.palette())
        actions: dict[object, str] = {}
        for identifier, title in self._sessions_provider():
            actions[menu.addAction(title)] = identifier
        if not actions:
            menu.addAction(NO_SESSIONS_LABEL).setEnabled(False)
        button = self._sessions_button
        # The button sits at the dock's right edge: align the menu's right edge with it.
        corner = button.mapToGlobal(button.rect().bottomRight())
        chosen = menu.exec(QPoint(corner.x() - menu.sizeHint().width(), corner.y() + MENU_GAP))
        menu.deleteLater()
        if chosen in actions:
            self.session_chosen.emit(actions[chosen])

    def replay(self, messages: list[dict[str, str]]) -> None:
        self.conversation.clear()
        for message in messages:
            if message.get("role") == "user":
                self.conversation.add_user_message(message.get("content", ""))
            else:
                self.conversation.add_assistant_message(message.get("content", ""))

    def add_user_message(self, text: str) -> int:
        return self.conversation.add_user_message(text)

    def add_system_message(self, text: str) -> int:
        return self.conversation.add_system_message(text)

    def add_result_message(self, text: str) -> int:
        return self.conversation.add_assistant_message(text)

    def add_stream_chunk(self, text: str) -> None:
        self.conversation.append_draft(text)

    def add_thinking_chunk(self, text: str) -> None:
        self.conversation.append_thinking(text)

    def finish_stream(self, markdown: str) -> bool:
        return self.conversation.finish_draft(markdown)

    def add_tool_message(self, text: str) -> int:
        self.progress.step(text)
        return self.conversation.add_activity_step(text)

    def add_rejected_message(self, text: str) -> int:
        return self.conversation.add_rejected_step(text)

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        self.conversation.mark_activity_step(message_id, ok)

    def add_plan_message(self, plan_lines: list[str]) -> int:
        return self.conversation.add_plan_card(plan_lines)

    def confirm_destructive(self, lines: list[str], details: str = "") -> bool:
        if (details or "").strip():
            return _confirm_code(self, lines, details)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("Destructive steps"))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(_destructive_confirmation_text(lines, details))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def confirm_data_sharing(self, endpoint: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("Share project data?"))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            tr(
                "Send the request to {0}?\n\n"
                "The provider receives your prompt and everything the agent reads to answer it: layer and "
                "field names, feature values, extents, layer sources and rendered map images. For data that "
                "must stay on this computer, use a local model server."
            ).format(endpoint)
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return box.exec() == QMessageBox.StandardButton.Yes

    def mark_plan_completed(self, message_id: int) -> None:
        self.conversation.mark_plan_applied(message_id)

    def mark_plan_failed(self, message_id: int) -> None:
        self.conversation.mark_plan_failed(message_id)

    def mark_plan_cancelled(self, message_id: int) -> None:
        self.conversation.mark_plan_cancelled(message_id)

    def set_busy(self, busy: bool) -> None:
        self.composer.set_busy(busy)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()

    def set_usage(self, text: str) -> None:
        self._usage_label.setText(text)

    def clear_prompt(self) -> None:
        self.composer.clear()


def _drawn(paint: Callable[[Any, int], QIcon], colour: Any, size: int) -> QIcon | None:
    try:
        icon = paint(colour, size)
    except Exception:
        return None
    return None if icon.isNull() else icon


def _confirm_code(parent: QWidget, lines: list[str], details: str) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("Destructive steps"))
    dialog.setMinimumWidth(720)
    column = QVBoxLayout(dialog)
    summary = QLabel(_destructive_steps_text(lines))
    summary.setTextFormat(Qt.TextFormat.PlainText)
    summary.setWordWrap(True)
    column.addWidget(summary)
    code_title = QLabel(tr("\n\nExact code to be executed:\n\n{0}").format("").strip())
    code_title.setTextFormat(Qt.TextFormat.PlainText)
    column.addWidget(code_title)
    code = QPlainTextEdit((details or "").strip())
    code.setReadOnly(True)
    code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    code.setMinimumHeight(240)
    column.addWidget(code)
    question = QLabel(tr("\n\nApply them?").strip())
    question.setTextFormat(Qt.TextFormat.PlainText)
    column.addWidget(question)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.No).setDefault(True)
    column.addWidget(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted


def _destructive_steps_text(lines: list[str]) -> str:
    listed = "\n".join(f"• {line}" for line in lines)
    return tr("These steps change or delete data and cannot be undone:\n\n{0}").format(listed)


def _destructive_confirmation_text(lines: list[str], details: str = "") -> str:
    message = _destructive_steps_text(lines)
    exact = (details or "").strip()
    if exact:
        message += tr("\n\nExact code to be executed:\n\n{0}").format(exact)
    return message + tr("\n\nApply them?")
