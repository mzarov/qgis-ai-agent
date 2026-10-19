import re
from typing import Any

from qgis.PyQt.QtCore import QEvent, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat
from qgis.PyQt.QtWidgets import QPlainTextEdit

from ai_agent.core.settings import WORK_MODE_ASK, WORK_MODE_AUTO, WORK_MODE_PLAN
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui.attachments import local_files
from ai_agent.ui.choice_popup import Choice

SKILL_TOKEN = re.compile(r"^/\S+")
LAYER_TOKEN = re.compile(r'(?:(?<=\s)|^)@(?:(?:point|area)\([^)\n]*\)?|"[^"]*"?|\S+)')
SLASH = "/"
MENTION = "@"
QUOTE = '"'
# Qt counts text positions in UTF-16 code units, Python in characters: 🌍 is two vs one.
UTF16 = "utf-16-le"
UTF16_UNIT = 2
MODES = (
    Choice(WORK_MODE_ASK, tr("Ask"), tr("Shows a plan and waits for Apply"), tr("Default")),
    Choice(WORK_MODE_AUTO, tr("Auto"), tr("Applies at once; deleting still asks")),
    Choice(WORK_MODE_PLAN, tr("Plan"), tr("Proposes a plan, changes nothing")),
)


def slash_query(text: str) -> str | None:
    if not text.startswith(SLASH) or any(character.isspace() for character in text):
        return None
    return text[len(SLASH) :]


def mention_query(text: str, cursor: int) -> tuple[int, str] | None:
    before = text[:cursor]
    start = before.rfind(MENTION)
    if start < 0 or (start > 0 and not before[start - 1].isspace()):
        return None
    query = before[start + len(MENTION) :]
    if any(character.isspace() or character == QUOTE for character in query):
        return None
    return start, query


def qt_length(text: str) -> int:
    return len(text.encode(UTF16)) // UTF16_UNIT


def text_before(text: str, position: int) -> str:
    return text.encode(UTF16)[: position * UTF16_UNIT].decode(UTF16)


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
    files_dropped = pyqtSignal(list)
    mode_cycled = pyqtSignal()
    new_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.popup_open = False

    def dragEnterEvent(self, event: Any) -> None:
        if local_files(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:
        if local_files(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:
        paths = local_files(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.files_dropped.emit(paths)

    def pad_vertically(self, pixels: int) -> None:
        self.setViewportMargins(0, pixels // 2, 0, pixels - pixels // 2)

    def event(self, event: Any) -> bool:
        # Claims Ctrl+N while focused: elsewhere the same keys make a new QGIS project.
        if event.type() == QEvent.Type.ShortcutOverride and controls.is_new_shortcut(event):
            event.accept()
            return True
        return super().event(event)

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event: Any) -> None:
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def keyPressEvent(self, event: Any) -> None:
        if controls.is_new_shortcut(event):
            self.new_requested.emit()
            return
        key = event.key()
        if self.popup_open and self._steer(key):
            return
        if key == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        if key == Qt.Key.Key_Backtab:
            self.mode_cycled.emit()
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
    def __init__(self, document: Any, palette: Any):
        super().__init__(document)
        self._skill = _token_format(palette, style.accent(palette))
        self._layer = _token_format(palette, style.success(palette))

    def highlightBlock(self, text: str) -> None:
        if self.currentBlock().blockNumber() == 0:
            match = SKILL_TOKEN.match(text)
            if match:
                self._light(text, match, self._skill)
        for match in LAYER_TOKEN.finditer(text):
            self._light(text, match, self._layer)

    def _light(self, text: str, match: Any, token: QTextCharFormat) -> None:
        # setFormat takes Qt positions, a match counts characters: an emoji would shift the colour.
        self.setFormat(qt_length(text[: match.start()]), qt_length(match.group()), token)


def _token_format(palette: Any, colour: Any) -> QTextCharFormat:
    token = QTextCharFormat()
    token.setForeground(colour)
    token.setBackground(style.soft(palette, colour))
    token.setFontWeight(QFont.Weight.DemiBold)
    return token
