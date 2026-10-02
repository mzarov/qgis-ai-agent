from collections.abc import Callable

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QTextCursor
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.composer_parts import (
    MENTION,
    SLASH,
    ComposerFrame,
    HintBar,
    PromptEdit,
    PromptHighlighter,
    mention_query,
    mention_text,
    slash_query,
)
from ai_agent.ui.skill_popup import SkillPopup

PLACEHOLDER = tr("Ask about the project…")
PLACEHOLDER_BUSY = tr("Type to correct me…")
PLACEHOLDER_OFFLINE = tr("Connect a model to start")
FRAME_NAME = "composerFrame"
FRAME_RADIUS = 14
FOCUS_WIDTH = 2
MIN_HEIGHT = 40
MAX_HEIGHT = 160
SEND_SIZE = 30
SEND_GLYPH = "↑"
STOP_GLYPH = "■"
MODE_SKILL = "skill"
MODE_LAYER = "layer"
KEY_SKILL = tr("skill")
KEY_LAYER = tr("layer")
KEY_SEND = tr("send")
KEY_NEW_LINE = tr("new line")
KEY_STOP = tr("stop")
SHIFT_ENTER = "⇧ Enter"
HINT_SKILLS = tr("Pick a skill")
HINT_LAYERS = tr("Pick a layer")
HINT_OFFLINE = tr("No model connected")


class Composer(QWidget):
    submitted = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._configured = True
        self._focused = False
        self._skills: Callable[[], list[tuple[str, str, str]]] = list
        self._layers: Callable[[], list[tuple[str, str, str]]] = list
        self._popup: SkillPopup | None = None
        self._mode = MODE_SKILL
        self._mention_start = 0
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self._frame = ComposerFrame(FRAME_RADIUS)
        self._frame.setObjectName(FRAME_NAME)
        self._send_look = ""
        inner = QVBoxLayout(self._frame)
        inner.setContentsMargins(12, 8, 8, 8)
        inner.setSpacing(4)
        inner.addWidget(self._build_edit())
        inner.addLayout(self._build_footer(palette))
        column.addWidget(self._frame)
        self._paint()

    def _build_edit(self) -> QPlainTextEdit:
        self._edit = PromptEdit()
        self._edit.setPlaceholderText(PLACEHOLDER)
        self._edit.setAccessibleName(tr("Request"))
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setStyleSheet("QPlainTextEdit { border: none; background: transparent; }")
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.setFixedHeight(MIN_HEIGHT)
        self._highlighter = PromptHighlighter(self._edit.document(), self.palette())
        self._edit.submitted.connect(self._on_submit)
        self._edit.navigated.connect(self._on_navigate)
        self._edit.accepted.connect(self._on_accept)
        self._edit.completed.connect(self._on_complete)
        self._edit.dismissed.connect(self._hide_popup)
        self._edit.escaped.connect(self._on_escape)
        self._edit.focus_changed.connect(self._on_focus)
        self._edit.textChanged.connect(self._on_text_changed)
        return self._edit

    def _build_footer(self, palette) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._hint = HintBar(palette)
        row.addWidget(self._hint, 1)
        self._send = QPushButton(SEND_GLYPH)
        self._send.setFixedSize(SEND_SIZE, SEND_SIZE)
        self._send.setToolTip(tr("Send"))
        self._send.setAccessibleName(tr("Send"))
        self._send.clicked.connect(self._on_button)
        row.addWidget(self._send)
        return row

    def _paint(self) -> None:
        """Frame, hint and button follow one state: offline, busy, typing or idle."""
        palette = self.palette()
        focused = self._focused and self._configured
        border = style.ring(palette) if focused else style.border_strong(palette)
        width = FOCUS_WIDTH if focused else style.HAIRLINE
        fill = style.surface(palette) if self._configured else style.card(palette)
        self._frame.set_look(fill.name(), border.name(), float(width))
        has_text = bool(self._edit.toPlainText().strip())
        # Offline, the welcome card already offers Open settings; a second button here only repeats it.
        self._send.setVisible(self._configured)
        if not self._configured:
            self._edit.setPlaceholderText(PLACEHOLDER_OFFLINE)
            self._hint.show_text(HINT_OFFLINE)
            return
        self._edit.setPlaceholderText(PLACEHOLDER_BUSY if self._busy else PLACEHOLDER)
        if self._edit.popup_open:
            self._hint.show_text(HINT_SKILLS if self._mode == MODE_SKILL else HINT_LAYERS)
        elif self._busy:
            self._hint.show_keys([("Esc", KEY_STOP)])
        elif has_text:
            self._hint.show_keys([("Enter", KEY_SEND), (SHIFT_ENTER, KEY_NEW_LINE)])
        else:
            self._hint.show_keys([(SLASH, KEY_SKILL), (MENTION, KEY_LAYER)])
        self._paint_send(has_text)

    def _paint_send(self, has_text: bool) -> None:
        palette = self.palette()
        if self._busy:
            fill, ink, glyph, name = style.text(palette), style.surface(palette), STOP_GLYPH, tr("Stop")
        elif has_text:
            fill, ink, glyph, name = style.accent(palette), style.on_accent(palette), SEND_GLYPH, tr("Send")
        else:
            fill, ink, glyph, name = style.card(palette), style.muted(palette), SEND_GLYPH, tr("Send")
        self._send.setText(glyph)
        self._send.setToolTip(name)
        self._send.setAccessibleName(name)
        look = (
            f"QPushButton {{ background: {style.css_color(fill)}; color: {style.css_color(ink)};"
            f"border: none; border-radius: {SEND_SIZE // 2}px; font-weight: 600; }}"
        )
        # Restyle only on a real change: a style sheet set per keystroke repolishes for nothing.
        if look != self._send_look:
            self._send_look = look
            self._send.setStyleSheet(look)

    def _on_focus(self, focused: bool) -> None:
        self._focused = focused
        self._paint()

    def _on_escape(self) -> None:
        if self._busy:
            self.stopped.emit()

    def set_configured(self, configured: bool) -> None:
        self._configured = configured
        self._edit.setReadOnly(not configured)
        self._paint()

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
            self._paint()
            return
        text = self._edit.toPlainText()
        query = slash_query(text)
        if query is not None:
            self._open_popup(MODE_SKILL, query, self._skills(), SLASH)
            return
        mention = mention_query(text, self._edit.textCursor().position())
        if mention is not None:
            self._mention_start = mention[0]
            self._open_popup(MODE_LAYER, mention[1], self._layers(), MENTION)
            return
        self._hide_popup()

    def _open_popup(self, mode: str, query: str, items: list[tuple[str, str, str]], prefix: str) -> None:
        if self._popup is None:
            return
        self._mode = mode
        self._popup.show_matches(query, items, self._frame, prefix)
        self._edit.popup_open = True
        self._paint()

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
        self._paint()

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
        self._paint()
