"""Pieces of the composer: the editor, /skill and @layer parsing, highlighting, the frame, the toolbar."""

import re
from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QToolButton, QWidget

from ai_agent.core.settings import WORK_MODE_ASK, WORK_MODE_AUTO
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui.attachments import local_files
from ai_agent.ui.choice_popup import Choice, ChoicePopup

SKILL_TOKEN = re.compile(r"^/\S+")
LAYER_TOKEN = re.compile(r'(?:(?<=\s)|^)@(?:"[^"]*"?|\S+)')
SLASH = "/"
MENTION = "@"
QUOTE = '"'
PLUS = "+"
TOOL_HEIGHT = 26
TOOL_RADIUS = 7
TOOL_GAP = 4
ATTACH = tr("Attach")
MODE_CAPTION = tr("Mode")
MODE_HINT = tr("How changes are applied. Shift+Tab switches.")
MODES = (
    Choice(WORK_MODE_ASK, tr("Ask first"), tr("Every change waits for Apply"), tr("Default")),
    Choice(WORK_MODE_AUTO, tr("Auto"), tr("Applies changes itself; deleting still asks")),
)
ADD_DATA = tr("Add data files…")
ATTACH_PICTURE = tr("Attach a picture…")
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
    files_dropped = pyqtSignal(list)
    mode_cycled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
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
        # Files are attached, not pasted as paths; any other drop is ordinary text.
        paths = local_files(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.files_dropped.emit(paths)

    def pad_vertically(self, pixels: int) -> None:
        """Split spare height evenly above and below the text, so one line sits centred."""
        self.setViewportMargins(0, pixels // 2, 0, pixels - pixels // 2)

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
        if key == Qt.Key.Key_Backtab:
            # Shift+Tab switches the mode, as in Claude Code; focus stays in the box.
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

    data_requested = pyqtSignal()
    picture_requested = pyqtSignal()
    mode_chosen = pyqtSignal(str)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 6, 4, 0)
        line.setSpacing(TOOL_GAP)
        self.attach = QToolButton()
        # Both buttons share one height and corner, so their hover plates line up.
        self.attach.setFixedSize(TOOL_HEIGHT, TOOL_HEIGHT)
        self.attach.setText(PLUS)
        self.attach.setToolTip(ATTACH)
        self.attach.setAccessibleName(ATTACH)
        self.attach.setAutoRaise(True)
        self.attach.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; padding: 0; border-radius: {TOOL_RADIUS}px;"
            f"color: {style.css_color(style.muted(palette))}; font-size: 16px; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(palette))};"
            f"color: {style.css_color(style.text(palette))}; }}"
        )
        self.menu = controls.menu(self.attach, palette)
        self.menu.addAction(ADD_DATA).triggered.connect(self.data_requested.emit)
        self.menu.addAction(ATTACH_PICTURE).triggered.connect(self.picture_requested.emit)
        self.attach.clicked.connect(self._open_menu)
        line.addWidget(self.attach, 0, Qt.AlignmentFlag.AlignVCenter)
        self.mode = QToolButton()
        self.mode.setFixedHeight(TOOL_HEIGHT)
        # As quiet as +, whatever the mode: the label says which one is on.
        self.mode.setStyleSheet(
            f"QToolButton {{ border: none; padding: 0 8px; border-radius: {TOOL_RADIUS}px; background: transparent;"
            f"color: {style.css_color(style.muted(palette))}; }}"
            f"QToolButton:hover {{ background: {style.css_color(style.card(palette))};"
            f"color: {style.css_color(style.text(palette))}; }}"
        )
        self.mode.setToolTip(MODE_HINT)
        self.mode.setAccessibleName(MODE_HINT)
        self.mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.modes = ChoicePopup(MODE_CAPTION, list(MODES), palette)
        self.modes.chosen.connect(self.mode_chosen.emit)
        self.mode.clicked.connect(lambda: self.modes.open_above(self.mode, self._mode))
        line.addWidget(self.mode, 0, Qt.AlignmentFlag.AlignVCenter)
        self._mode = WORK_MODE_ASK
        self.set_mode(WORK_MODE_ASK)
        line.addStretch(1)
        self.model = QLabel()
        self.model.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        # A tool button takes the platform's smaller font; the mode reads at the model name's size.
        self.mode.setFont(self.model.font())
        line.addWidget(self.model)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.mode.setText(next((choice.title for choice in MODES if choice.key == mode), MODES[0].title))

    def set_model(self, name: str) -> None:
        self.model.setText(name.rsplit("/", 1)[-1] if name else NO_MODEL)
        self.model.setToolTip(name or NO_MODEL)

    def _open_menu(self) -> None:
        # The composer sits at the bottom of the dock: the menu opens upwards, above the button.
        above = self.attach.mapToGlobal(QPoint(0, 0))
        self.menu.popup(QPoint(above.x(), above.y() - self.menu.sizeHint().height() - controls.MENU_GAP))
