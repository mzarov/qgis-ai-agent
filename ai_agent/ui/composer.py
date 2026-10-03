from collections.abc import Callable
from typing import Any

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
from ai_agent.ui import controls, style
from ai_agent.ui.attachments import DATA, PICTURE, AttachmentChips, choose_files
from ai_agent.ui.composer_parts import (
    MENTION,
    MODES,
    SLASH,
    ComposerToolbar,
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
MAX_LINES = 8
HEIGHT_SLACK = 4
SEND_SIZE = 28
SEND_RADIUS = 7
SEND_GLYPH = "↵"
STOP_GLYPH = "■"
MODE_SKILL = "skill"
MODE_LAYER = "layer"


class Composer(QWidget):
    submitted = pyqtSignal(str)
    stopped = pyqtSignal()
    files_attached = pyqtSignal(list)
    mode_changed = pyqtSignal(str)

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

        self._frame = controls.RoundedFrame(FRAME_RADIUS)
        self._frame.setObjectName(FRAME_NAME)
        self._send_look = ""
        framed = QVBoxLayout(self._frame)
        framed.setContentsMargins(0, 0, 0, 0)
        framed.setSpacing(0)
        self.attachments = AttachmentChips(palette)
        self.attachments.setContentsMargins(8, 6, 8, 0)
        framed.addWidget(self.attachments)
        # One row like Claude Code: the text grows line by line, the button stays at the bottom right.
        inner = QHBoxLayout()
        inner.setContentsMargins(12, 6, 6, 6)
        inner.setSpacing(8)
        inner.addWidget(self._build_edit(), 1, Qt.AlignmentFlag.AlignVCenter)
        inner.addWidget(self._build_send(), 0, Qt.AlignmentFlag.AlignBottom)
        framed.addLayout(inner)
        column.addWidget(self._frame)
        self.toolbar = ComposerToolbar(palette)
        self.toolbar.set_model("")
        self.toolbar.data_requested.connect(lambda: self._choose(DATA))
        self.toolbar.picture_requested.connect(lambda: self._choose(PICTURE))
        self.toolbar.mode_chosen.connect(self._on_mode)
        column.addWidget(self.toolbar)
        self._paint()

    def _build_edit(self) -> QPlainTextEdit:
        self._edit = PromptEdit()
        self._edit.setPlaceholderText(PLACEHOLDER)
        self._edit.setAccessibleName(tr("Request"))
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setStyleSheet("QPlainTextEdit { border: none; background: transparent; }")
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The few spare pixels that keep the scroll bar away go half above, half below the text.
        self._edit.pad_vertically(HEIGHT_SLACK)
        self._edit.document().documentLayout().documentSizeChanged.connect(self._grow)
        self._highlighter = PromptHighlighter(self._edit.document(), self.palette())
        self._edit.submitted.connect(self._on_submit)
        self._edit.navigated.connect(self._on_navigate)
        self._edit.accepted.connect(self._on_accept)
        self._edit.completed.connect(self._on_complete)
        self._edit.dismissed.connect(self._hide_popup)
        self._edit.escaped.connect(self._on_escape)
        self._edit.files_dropped.connect(self.files_attached.emit)
        self._edit.mode_cycled.connect(self._next_mode)
        self._edit.focus_changed.connect(self._on_focus)
        self._edit.textChanged.connect(self._on_text_changed)
        self._grow()
        return self._edit

    def _build_send(self) -> QPushButton:
        self._send = QPushButton(SEND_GLYPH)
        self._send.setFixedSize(SEND_SIZE, SEND_SIZE)
        self._send.clicked.connect(self._on_button)
        return self._send

    def _paint(self) -> None:
        """Frame, hint and button follow one state: offline, busy, typing or idle."""
        palette = self.palette()
        focused = self._focused and self._configured
        border = style.faint(palette) if focused else style.border_strong(palette)
        fill = style.surface(palette) if self._configured else style.card(palette)
        self._frame.set_look(fill.name(), border.name())
        has_text = bool(self._edit.toPlainText().strip())
        self._send.setVisible(self._configured)
        if not self._configured:
            self._edit.setPlaceholderText(PLACEHOLDER_OFFLINE)
            return
        self._edit.setPlaceholderText(PLACEHOLDER_BUSY if self._busy else PLACEHOLDER)
        self._paint_send(has_text)

    def _paint_send(self, has_text: bool) -> None:
        """A bare glyph as in Claude Code: dim and disabled with nothing to send, bright once there is,
        and a rounded plate only under the pointer."""
        palette = self.palette()
        active = self._busy or has_text
        glyph, name = (STOP_GLYPH, tr("Stop")) if self._busy else (SEND_GLYPH, tr("Send"))
        self._send.setEnabled(active)
        self._send.setText(glyph)
        self._send.setToolTip(name)
        self._send.setAccessibleName(name)
        look = (
            f"QPushButton {{ background: transparent; color: {style.css_color(style.text(palette))};"
            f"border: none; border-radius: {SEND_RADIUS}px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
            f"QPushButton:disabled {{ color: {style.css_color(style.faint(palette))}; background: transparent; }}"
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

    def set_model(self, name: str) -> None:
        self.toolbar.set_model(name)

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

    def _grow(self, *_args: Any) -> None:
        """Fit the editor to its wrapped lines, one line at least and MAX_LINES at most."""
        try:
            wanted = max(1, int(round(float(self._edit.document().size().height()))))
            margin = 2 * float(self._edit.document().documentMargin()) + 2 * float(self._edit.frameWidth())
            line = float(self._line_height())
        except (TypeError, ValueError):
            return
        lines = min(MAX_LINES, wanted)
        self._edit.setFixedHeight(int(lines * line + margin + HEIGHT_SLACK))
        # A scroll bar only once the text outgrows the cap; below it the box simply grows.
        policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded if wanted > MAX_LINES else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self._edit.setVerticalScrollBarPolicy(policy)

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

    def _choose(self, kind: str) -> None:
        paths = choose_files(self, kind)
        if paths:
            self.files_attached.emit(paths)

    @property
    def mode(self) -> str:
        return self.toolbar._mode

    def set_mode(self, mode: str) -> None:
        """Show the stored mode without reporting it back as a change."""
        self.toolbar.set_mode(mode)

    def _on_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.toolbar.set_mode(mode)
            self.mode_changed.emit(mode)

    def _next_mode(self) -> None:
        keys = [choice.key for choice in MODES]
        position = keys.index(self.mode) if self.mode in keys else 0
        self._on_mode(keys[(position + 1) % len(keys)])

    def add_attachment(self, path: str) -> None:
        self.attachments.add(path)

    def take_attachments(self) -> list[str]:
        return self.attachments.take()

    def mention_layers(self, names: list[str]) -> None:
        """Put @mentions of freshly added layers at the cursor, so the request names them."""
        cursor = self._edit.textCursor()
        before = self._edit.toPlainText()[: cursor.position()]
        lead = "" if not before or before[-1].isspace() else " "
        cursor.insertText(lead + " ".join(mention_text(name) for name in names) + " ")
        self._edit.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._paint()
