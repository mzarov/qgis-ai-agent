"""Pieces of the composer: the editor, /skill and @layer parsing, highlighting, the frame, the toolbar."""

import re
from typing import Any

from qgis.PyQt.QtCore import QPoint, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPen, QSyntaxHighlighter, QTextCharFormat
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QToolButton, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import style

SKILL_TOKEN = re.compile(r"^/\S+")
LAYER_TOKEN = re.compile(r'(?:(?<=\s)|^)@(?:"[^"]*"?|\S+)')
SLASH = "/"
MENTION = "@"
QUOTE = '"'
PLUS = "+"
MENU_GAP = 4
ATTACH = tr("Attach")
ATTACH_SOON = tr("Attaching files is coming soon")
NO_MODEL = tr("No model")


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


class ComposerToolbar(QWidget):
    """The row under the composer: + on the left, the model's name on the right."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 6, 4, 0)
        line.setSpacing(2)
        self.attach = QToolButton()
        self.attach.setText(PLUS)
        self.attach.setToolTip(ATTACH)
        self.attach.setAccessibleName(ATTACH)
        self.attach.setAutoRaise(True)
        self.attach.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; padding: 2px 8px; border-radius: 7px;"
            f"color: {style.css_color(style.muted(palette))}; font-size: 16px; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(palette))};"
            f"color: {style.css_color(style.text(palette))}; }}"
        )
        self.menu = QMenu(self.attach)
        soon = self.menu.addAction(ATTACH_SOON)
        soon.setEnabled(False)
        self.attach.clicked.connect(self._open_menu)
        line.addWidget(self.attach)
        line.addStretch(1)
        self.model = QLabel()
        self.model.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        line.addWidget(self.model)

    def set_model(self, name: str) -> None:
        self.model.setText(name.rsplit("/", 1)[-1] if name else NO_MODEL)
        self.model.setToolTip(name or NO_MODEL)

    def _open_menu(self) -> None:
        # The composer sits at the bottom of the dock: the menu opens upwards, above the button.
        above = self.attach.mapToGlobal(QPoint(0, 0))
        self.menu.popup(QPoint(above.x(), above.y() - self.menu.sizeHint().height() - MENU_GAP))


class ComposerFrame(QFrame):
    """The composer's rounded box, painted by hand.

    It used to restyle itself with a style sheet on every focus change. A style
    sheet on the frame cascades to the editor inside it, so the editor's style
    was swapped while its own focusOutEvent was still running, and QGIS crashed
    in event processing. Painting needs only `update()`.
    """

    def __init__(self, radius: float, parent: QWidget | None = None):
        super().__init__(parent)
        self._radius = radius
        self._fill: Any = None
        self._border: Any = None
        self._width = 1.0

    def set_look(self, fill: Any, border: Any, width: float) -> None:
        if (fill, border, width) == (self._fill, self._border, self._width):
            return
        self._fill, self._border, self._width = fill, border, width
        self.update()

    def paintEvent(self, _event: Any) -> None:
        if self._fill is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._border))
        pen.setWidthF(self._width)
        painter.setPen(pen)
        painter.setBrush(QColor(self._fill))
        inset = self._width / 2 + (2 - self._width) / 2
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), self._radius, self._radius)
        painter.end()
