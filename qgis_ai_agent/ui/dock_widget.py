from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase, QIcon
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.ui import icons, style
from qgis_ai_agent.ui.composer import Composer
from qgis_ai_agent.ui.conversation import ConversationView

TITLE = "QGIS AI Agent"
NEW_SESSION_LABEL = tr("New conversation")
NO_SESSIONS_LABEL = tr("No past conversations")
HEADER_MARGINS = (11, 8, 9, 8)
HEADER_ICON = 15
HEADER_BUTTON = 24
BODY_MARGINS = (9, 0, 9, 9)


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
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self._build_conversation(), 1)
        column.addWidget(self._build_composer())
        self.setWidget(body)

    def _build_header(self) -> QWidget:
        header = QWidget()
        palette = self.palette()
        header.setStyleSheet(f"border-bottom: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};")
        row = QHBoxLayout(header)
        row.setContentsMargins(*HEADER_MARGINS)
        row.setSpacing(4)

        title = QLabel(TITLE)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("border: none;")
        row.addWidget(title, 1)
        self._usage_label = QLabel("")
        self._usage_label.setStyleSheet(f"border: none; color: {style.css_color(style.muted(palette))};")
        row.addWidget(self._usage_label)
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

    def _build_conversation(self) -> QWidget:
        self.conversation = ConversationView()
        self.conversation.confirm_requested.connect(self.confirm_plan_clicked.emit)
        self.conversation.cancel_requested.connect(self.cancel_plan_clicked.emit)
        self.conversation.suggestion_chosen.connect(self.prompt_submitted.emit)
        self.conversation.settings_requested.connect(self.open_settings_clicked.emit)
        return self.conversation

    def _build_composer(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(*BODY_MARGINS)
        self.composer = Composer()
        self.composer.submitted.connect(self.prompt_submitted.emit)
        self.composer.stopped.connect(self.stop_clicked.emit)
        layout.addWidget(self.composer)
        return holder

    def set_session_source(self, provider: Callable[[], list[tuple[str, str]]]) -> None:
        self._sessions_provider = provider

    def _show_sessions(self) -> None:
        menu = QMenu(self)
        fresh = menu.addAction(NEW_SESSION_LABEL)
        menu.addSeparator()
        actions: dict[object, str] = {}
        for identifier, title in self._sessions_provider():
            actions[menu.addAction(title)] = identifier
        if not actions:
            menu.addAction(NO_SESSIONS_LABEL).setEnabled(False)
        button = self._sessions_button
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen is fresh:
            self.new_session_clicked.emit()
        elif chosen in actions:
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
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("Share project data?"))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            tr(
                "The request will be sent to {0}.\n\n"
                "The provider may receive your prompt, layer and field names, CRS, project notes, "
                "tool results and generated plans. Feature values, exact extents, layer sources and filters, "
                "Processing or Python results, and rendered images remain blocked unless you separately "
                "enable sensitive data in Settings.\n\n"
                "Continue and remember this choice for this endpoint?"
            ).format(endpoint)
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def mark_plan_completed(self, message_id: int) -> None:
        self.conversation.mark_plan_applied(message_id)

    def mark_plan_failed(self, message_id: int) -> None:
        self.conversation.mark_plan_failed(message_id)

    def mark_plan_cancelled(self, message_id: int) -> None:
        self.conversation.mark_plan_cancelled(message_id)

    def set_busy(self, busy: bool) -> None:
        self.composer.set_busy(busy)

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
    summary.setWordWrap(True)
    column.addWidget(summary)
    code_title = QLabel(tr("\n\nExact code to be executed:\n\n{0}").format("").strip())
    column.addWidget(code_title)
    code = QPlainTextEdit((details or "").strip())
    code.setReadOnly(True)
    code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    code.setMinimumHeight(240)
    column.addWidget(code)
    question = QLabel(tr("\n\nApply them?").strip())
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
