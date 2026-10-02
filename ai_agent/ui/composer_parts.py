"""Pieces of the composer: the editor, /skill and @layer parsing, highlighting, the key hints."""

import re
from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QWidget

from ai_agent.ui import controls, style

SKILL_TOKEN = re.compile(r"^/\S+")
LAYER_TOKEN = re.compile(r'(?:(?<=\s)|^)@(?:"[^"]*"?|\S+)')
SLASH = "/"
MENTION = "@"
QUOTE = '"'
HINT_GAP = 5
PAIR_GAP = 10


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
    escaped = pyqtSignal()
    focus_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup_open = False

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event: Any) -> None:
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def keyPressEvent(self, event: Any) -> None:
        key = event.key()
        if self.popup_open and self._steer(key):
            return
        if key == Qt.Key.Key_Escape:
            self.escaped.emit()
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


class PromptHighlighter(QSyntaxHighlighter):
    """Paint the leading /skill and every @layer the way the popup shows them."""

    def __init__(self, document: Any, palette: Any):
        super().__init__(document)
        self._skill = _token_format(palette, style.accent(palette))
        self._layer = _token_format(palette, style.success(palette))

    def highlightBlock(self, text: str) -> None:
        if self.currentBlock().blockNumber() == 0:
            match = SKILL_TOKEN.match(text)
            if match:
                self.setFormat(match.start(), match.end() - match.start(), self._skill)
        for match in LAYER_TOKEN.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self._layer)


def _token_format(palette: Any, colour: Any) -> QTextCharFormat:
    token = QTextCharFormat()
    token.setForeground(colour)
    token.setBackground(style.soft(palette, colour))
    token.setFontWeight(QFont.Weight.DemiBold)
    return token


class HintBar(QWidget):
    """Keycaps with a word after each, or one plain line; rebuilt when the composer changes state."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(0, 0, 0, 0)
        self._line.setSpacing(HINT_GAP)
        self._parts: list[QWidget] = []
        self._line.addStretch(1)
        self.text = ""

    def show_keys(self, pairs: list[tuple[str, str]]) -> None:
        self._clear()
        for index, (key, word) in enumerate(pairs):
            cap = controls.keycap(key, self._palette)
            if index:
                cap.setContentsMargins(PAIR_GAP - HINT_GAP, 0, 0, 0)
            self._add(cap)
            self._add(self._word(word))
        self.text = "  ".join(f"{key} {word}" for key, word in pairs)

    def show_text(self, text: str) -> None:
        self._clear()
        self._add(self._word(text))
        self.text = text

    def _word(self, text: str) -> QLabel:
        label = controls.small(text, self._palette)
        label.setWordWrap(False)
        label.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))}; border: none;")
        return label

    def _add(self, widget: QWidget) -> None:
        # Insert before the trailing stretch so the hints hug the left edge.
        self._line.insertWidget(len(self._parts), widget)
        self._parts.append(widget)

    def _clear(self) -> None:
        for widget in self._parts:
            self._line.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        self._parts = []
