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

PLACEHOLDER = tr("Ask about the project; / picks a skill, @ picks a layer")
MIN_HEIGHT = 34
MAX_HEIGHT = 120
SEND_SIZE = 26
HINT_FONT_SCALE = 0.85
SEND_GLYPH = "↑"
STOP_GLYPH = "■"
SLASH = "/"
MENTION = "@"
QUOTE = '"'
MODE_SKILL = "skill"
MODE_LAYER = "layer"
HINT_IDLE = tr("Enter to send, Shift+Enter for a new line")
HINT_BUSY = tr("Working… type to correct me, or press ■ to stop")
HINT_SKILLS = tr("↑↓ to choose a skill, Tab or Enter to insert, Esc to dismiss")
HINT_LAYERS = tr("↑↓ to choose a layer, Tab or Enter to insert, Esc to dismiss")


def slash_query(text: str) -> str | None:
    if not text.startswith(SLASH) or any(character.isspace() for character in text):
        return None
    return text[len(SLASH) :]


def mention_query(text: str, cursor: int) -> tuple[int, str] | None:
    """Return where an unfinished @mention starts before the cursor, and its text.

    A mention starts at an @ that opens the text or follows whitespace and runs
    to the cursor without whitespace, so an e-mail address is never a mention.
    """
    before = text[:cursor]
    start = before.rfind(MENTION)
    if start < 0 or (start > 0 and not before[start - 1].isspace()):
        return None
    query = before[start + len(MENTION) :]
    if any(character.isspace() or character == QUOTE for character in query):
        return None
    return start, query


def mention_text(name: str) -> str:
    if any(character.isspace() for character in name):
        return f"{MENTION}{QUOTE}{name}{QUOTE}"
    return f"{MENTION}{name}"


class PromptEdit(QPlainTextEdit):
    submitted = pyqtSignal()
    navigated = pyqtSignal(int)
    accepted = pyqtSignal()
    completed = pyqtSignal()
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
        elif key == Qt.Key.Key_Tab:
            self.completed.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
        self._layers: Callable[[], list[tuple[str, str, str]]] = list
        self._popup: SkillPopup | None = None
        self._mode = MODE_SKILL
        self._mention_start = 0
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
        self._edit.setAccessibleName(tr("Request"))
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setStyleSheet("border: none; background: transparent;")
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.setFixedHeight(MIN_HEIGHT)
        self._edit.submitted.connect(self._on_submit)
        self._edit.navigated.connect(self._on_navigate)
        self._edit.accepted.connect(self._on_accept)
        self._edit.completed.connect(self._on_complete)
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
        self._send.setAccessibleName(tr("Send"))
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

    def set_layer_source(self, provider: Callable[[], list[tuple[str, str, str]]]) -> None:
        self._layers = provider

    def set_popup_host(self, host: QWidget) -> None:
        self._popup = SkillPopup(host)
        self._popup.chosen.connect(self._insert_choice)

    def _on_text_changed(self) -> None:
        self._grow()
        if self._popup is None:
            return
        text = self._edit.toPlainText()
        query = slash_query(text)
        if query is not None:
            self._open_popup(MODE_SKILL, query, self._skills(), SLASH, HINT_SKILLS)
            return
        mention = mention_query(text, self._edit.textCursor().position())
        if mention is not None:
            self._mention_start = mention[0]
            self._open_popup(MODE_LAYER, mention[1], self._layers(), MENTION, HINT_LAYERS)
            return
        self._hide_popup()

    def _open_popup(self, mode: str, query: str, items: list[tuple[str, str, str]], prefix: str, hint: str) -> None:
        if self._popup is None:
            return
        self._mode = mode
        self._popup.show_matches(query, items, self._edit, prefix)
        self._edit.popup_open = True
        self._hint.setText(hint)

    def _on_navigate(self, delta: int) -> None:
        if self._popup is not None:
            self._popup.move_selection(delta)

    def _on_accept(self) -> None:
        if self._popup is None or not self._popup.choose_current():
            self._hide_popup()
            self._on_submit()

    def _on_complete(self) -> None:
        if self._popup is not None:
            self._popup.choose_current()

    def _insert_choice(self, name: str) -> None:
        if self._mode == MODE_LAYER:
            self._insert_layer(name)
        else:
            self._insert_skill(name)

    def _insert_skill(self, name: str) -> None:
        self._edit.setPlainText(f"{SLASH}{name} ")
        self._edit.moveCursor(QTextCursor.MoveOperation.End)
        self._hide_popup()

    def _insert_layer(self, name: str) -> None:
        text = self._edit.toPlainText()
        cursor = self._edit.textCursor().position()
        inserted = mention_text(name) + " "
        self._edit.setPlainText(text[: self._mention_start] + inserted + text[cursor:])
        moved = self._edit.textCursor()
        moved.setPosition(self._mention_start + len(inserted))
        self._edit.setTextCursor(moved)
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

    def restore(self, text: str) -> None:
        if text and not self._edit.toPlainText().strip():
            self._edit.setPlainText(text)
            self._edit.moveCursor(QTextCursor.MoveOperation.End)
        self._edit.setFocus()

    def focus(self) -> None:
        self._edit.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        palette = self.palette()
        self._send.setText(STOP_GLYPH if busy else SEND_GLYPH)
        self._send.setToolTip(tr("Stop") if busy else tr("Send"))
        self._send.setAccessibleName(tr("Stop") if busy else tr("Send"))
        self._send.setStyleSheet(self._button_style(style.danger(palette) if busy else style.accent(palette)))
        self._hint.setText(HINT_BUSY if busy else HINT_IDLE)
