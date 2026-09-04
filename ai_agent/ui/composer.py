from collections.abc import Callable
from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QTextCursor
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.skill_popup import SkillPopup

PLACEHOLDER = tr("Ask about the project, or type / to pick a skill")
MIN_HEIGHT = 34
MAX_HEIGHT = 120
SEND_SIZE = 26
HINT_FONT_SCALE = 0.85
SEND_GLYPH = "↑"
STOP_GLYPH = "■"
SLASH = "/"
HINT_IDLE = tr("Enter to send, Shift+Enter for a new line")
HINT_BUSY = tr("Working… type to correct me, or press ■ to stop")
HINT_SKILLS = tr("↑↓ to choose a skill, Tab or Enter to insert, Esc to dismiss")


def slash_query(text: str) -> str | None:
    if not text.startswith(SLASH) or any(character.isspace() for character in text):
        return None
    return text[len(SLASH) :]


class PromptEdit(QPlainTextEdit):
    submitted = pyqtSignal()
    navigated = pyqtSignal(int)
    accepted = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup_open = False

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if self.popup_open and self._steer(key):
            return
        enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        plain = not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if enter and plain:
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def _steer(self, key: Any) -> bool:
        if key == Qt.Key.Key_Up:
            self.navigated.emit(-1)
        elif key == Qt.Key.Key_Down:
            self.navigated.emit(1)
        elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accepted.emit()
        elif key == Qt.Key.Key_Escape:
            self.dismissed.emit()
        else:
            return False
        return True


class Composer(QWidget):
    submitted = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._skills: Callable[[], list[tuple[str, str, str]]] = list
        self._popup: SkillPopup | None = None
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        frame = QWidget()
        frame.setStyleSheet(
            f"background: {style.css_color(style.surface(palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {style.BUBBLE_RADIUS}px;"
        )
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(9, 7, 8, 7)
        inner.setSpacing(5)
        inner.addWidget(self._build_edit())
        inner.addLayout(self._build_footer(palette))
        column.addWidget(frame)

    def _build_edit(self) -> QPlainTextEdit:
        self._edit = PromptEdit()
        self._edit.setPlaceholderText(PLACEHOLDER)
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setStyleSheet("border: none; background: transparent;")
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.setFixedHeight(MIN_HEIGHT)
        self._edit.submitted.connect(self._on_submit)
        self._edit.navigated.connect(self._on_navigate)
        self._edit.accepted.connect(self._on_accept)
        self._edit.dismissed.connect(self._hide_popup)
        self._edit.textChanged.connect(self._on_text_changed)
        return self._edit

    def _build_footer(self, palette) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._hint = QLabel(HINT_IDLE)
        font = self._hint.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_FONT_SCALE))
        self._hint.setFont(font)
        self._hint.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        row.addWidget(self._hint, 1)

        self._send = QPushButton(SEND_GLYPH)
        self._send.setFixedSize(SEND_SIZE, SEND_SIZE)
        self._send.setToolTip(tr("Send"))
        self._send.setStyleSheet(self._button_style(style.accent(palette)))
        self._send.clicked.connect(self._on_button)
        row.addWidget(self._send)
        return row

    def _button_style(self, fill) -> str:
        return (
            f"QPushButton {{ background: {style.css_color(fill)};"
            f"color: {style.css_color(self.palette().highlightedText().color())};"
            f"border: none; border-radius: {SEND_SIZE // 2}px; }}"
        )

    def set_skill_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self._skills = provider

    def set_popup_host(self, host: QWidget) -> None:
        self._popup = SkillPopup(host)
        self._popup.chosen.connect(self._insert_skill)

    def _on_text_changed(self) -> None:
        self._grow()
        query = slash_query(self._edit.toPlainText())
        if query is None or self._popup is None:
            self._hide_popup()
            return
        self._popup.show_matches(query, self._skills(), self._edit)
        self._edit.popup_open = True
        self._hint.setText(HINT_SKILLS)

    def _on_navigate(self, delta: int) -> None:
        if self._popup is not None:
            self._popup.move_selection(delta)

    def _on_accept(self) -> None:
        if self._popup is None or not self._popup.choose_current():
            self._hide_popup()
            self._on_submit()

    def _insert_skill(self, name: str) -> None:
        self._edit.setPlainText(f"{SLASH}{name} ")
        self._edit.moveCursor(QTextCursor.MoveOperation.End)
        self._hide_popup()

    def _hide_popup(self) -> None:
        if self._popup is not None:
            self._popup.hide()
        self._edit.popup_open = False
        self._hint.setText(HINT_BUSY if self._busy else HINT_IDLE)

    def _on_button(self) -> None:
        if self._busy:
            self.stopped.emit()
            return
        self._on_submit()

    def _grow(self) -> None:
        height = int(self._edit.document().size().height() * self._line_height()) + 12
        self._edit.setFixedHeight(max(MIN_HEIGHT, min(height, MAX_HEIGHT)))

    def _line_height(self) -> float:
        return self._edit.fontMetrics().lineSpacing()

    def _on_submit(self) -> None:
        text = self._edit.toPlainText().strip()
        if text:
            self.submitted.emit(text)

    def clear(self) -> None:
        self._edit.clear()
        self._hide_popup()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        palette = self.palette()
        self._send.setText(STOP_GLYPH if busy else SEND_GLYPH)
        self._send.setToolTip(tr("Stop") if busy else tr("Send"))
        self._send.setStyleSheet(self._button_style(style.danger(palette) if busy else style.accent(palette)))
        self._hint.setText(HINT_BUSY if busy else HINT_IDLE)
