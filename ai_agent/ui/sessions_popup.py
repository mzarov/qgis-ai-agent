"""The history menu under the conversation's title: a new conversation, then the past ones by day.

"New conversation" with its shortcut comes first, then the project's
conversations grouped Today, Yesterday and Earlier, newest first, each with its
time or date on the right; the open one is lit. Hovering a row swaps the time
for a pencil (rename in place: Enter keeps, Esc drops) and a bin (delete, after
the dock confirms, because deleting is for good). Rows paint their hover, so
nothing restyles while a mouse event runs.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QKeySequence
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

POPUP_WIDTH = 320
POPUP_RADIUS = 8
POPUP_PADDING = 4
ROW_RADIUS = 5
ROW_HEIGHT = 30
MAX_LIST_HEIGHT = 420
ICON = 14
ICON_BUTTON = 22
NEW_ICON = 16
META_SCALE = 11.5 / 13
TIME_FORMAT = "%H:%M"
DATE_FORMAT = "%d.%m"
OLD_DATE_FORMAT = "%d.%m.%Y"
FALLBACK_SHORTCUT = "Ctrl+N"
RENAME = tr("Rename")
DELETE = tr("Delete")
NO_SESSIONS = tr("No conversations yet")
NEW_CONVERSATION = tr("New conversation")
TODAY = tr("Today")
YESTERDAY = tr("Yesterday")
EARLIER = tr("Earlier")


@dataclass(frozen=True)
class Entry:
    """One conversation as the menu lists it; `updated` is a Unix time."""

    identifier: str
    title: str
    updated: float = 0.0
    current: bool = False


def day_groups(entries: list[Entry], now: float) -> list[tuple[str, list[tuple[Entry, str]]]]:
    """The entries by day, newest first, each with what its row shows on the right: a time or a date."""
    today = datetime.fromtimestamp(now).date()
    grouped: dict[str, list[tuple[Entry, str]]] = {}
    for entry in sorted(entries, key=lambda item: item.updated, reverse=True):
        moment = datetime.fromtimestamp(entry.updated)
        day = moment.date()
        # A clock that ran ahead still counts as today.
        if day >= today:
            label, meta = TODAY, moment.strftime(TIME_FORMAT)
        elif day == today - timedelta(days=1):
            label, meta = YESTERDAY, moment.strftime(TIME_FORMAT)
        else:
            label, meta = EARLIER, moment.strftime(DATE_FORMAT if day.year == today.year else OLD_DATE_FORMAT)
        grouped.setdefault(label, []).append((entry, meta))
    return [(label, grouped[label]) for label in (TODAY, YESTERDAY, EARLIER) if label in grouped]


def new_shortcut() -> str:
    """The new-conversation shortcut as this platform writes it (⌘N on macOS)."""
    try:
        text = QKeySequence(QKeySequence.StandardKey.New).toString(QKeySequence.SequenceFormat.NativeText)
    except Exception:
        return FALLBACK_SHORTCUT
    return text if isinstance(text, str) and text else FALLBACK_SHORTCUT


class SessionRow(controls.RoundedFrame):
    chosen = pyqtSignal(str)
    renamed = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str, str)

    def __init__(self, entry: Entry, meta: str, palette: Any, parent: QWidget | None = None):
        super().__init__(ROW_RADIUS, parent)
        self.identifier = entry.identifier
        self.title = entry.title
        self.current = entry.current
        self._fill = style.card(palette).name()
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 0, 4, 0)
        line.setSpacing(2)
        self.label = controls.ElidedLabel(entry.title)
        if entry.current:
            font = self.label.font()
            font.setWeight(QFont.Weight.Medium)
            self.label.setFont(font)
        style.ink(self.label, style.text(palette))
        line.addWidget(self.label, 1)
        self.editor = QLineEdit(entry.title)
        self.editor.setStyleSheet(fields.input_style(palette))
        self.editor.setVisible(False)
        self.editor.returnPressed.connect(self._keep_name)
        line.addWidget(self.editor, 1)
        self.meta = QLabel(meta)
        style.scale_font(self.meta, META_SCALE)
        style.ink(self.meta, style.faint(palette))
        self.meta.setContentsMargins(0, 0, 6, 0)
        line.addWidget(self.meta)
        muted = style.muted(palette)
        self.rename_button = controls.icon_button("rename", "✎", RENAME, muted, palette, ICON_BUTTON, ICON, ROW_RADIUS)
        self.rename_button.clicked.connect(self.start_rename)
        line.addWidget(self.rename_button)
        self.delete_button = controls.icon_button("delete", "🗑", DELETE, muted, palette, ICON_BUTTON, ICON, ROW_RADIUS)
        self.delete_button.clicked.connect(self._ask_delete)
        line.addWidget(self.delete_button)
        self._show_actions(False)
        self._paint(False)

    def _show_actions(self, shown: bool) -> None:
        """The row under the pointer trades its time for the pencil and the bin."""
        self.rename_button.setVisible(shown and not self.editor.isVisible())
        self.delete_button.setVisible(shown)
        self.meta.setVisible(not shown)

    def _paint(self, hovered: bool) -> None:
        self.set_look(self._fill if hovered or self.current else None, None)

    def _ask_delete(self) -> None:
        self.delete_requested.emit(self.identifier, self.title)

    def start_rename(self) -> None:
        self.label.setVisible(False)
        self.rename_button.setVisible(False)
        self.editor.setText(self.title)
        self.editor.setVisible(True)
        self.editor.selectAll()
        self.editor.setFocus()

    def stop_rename(self) -> None:
        self.editor.setVisible(False)
        self.label.setVisible(True)

    def _keep_name(self) -> None:
        name = self.editor.text().strip()
        self.stop_rename()
        if name and name != self.title:
            self.title = name
            self.label.setText(name)
            self.label.setToolTip(name)
            self.renamed.emit(self.identifier, name)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape and self.editor.isVisible():
            self.stop_rename()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.editor.isVisible():
            self.chosen.emit(self.identifier)

    def enterEvent(self, event: Any) -> None:
        self._paint(True)
        self._show_actions(True)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._paint(False)
        if not self.editor.isVisible():
            self._show_actions(False)
        super().leaveEvent(event)


class NewRow(controls.HoverFrame):
    """The menu's first row: a plus, "New conversation", the shortcut."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(ROW_RADIUS, palette, parent)
        self.setFixedHeight(ROW_HEIGHT)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 0, 10, 0)
        line.setSpacing(10)
        line.addWidget(controls.glyph("new", style.faint(palette), NEW_ICON))
        title = QLabel(NEW_CONVERSATION)
        style.ink(title, style.text(palette))
        line.addWidget(title, 1)
        self.shortcut = QLabel(new_shortcut())
        style.scale_font(self.shortcut, META_SCALE)
        style.ink(self.shortcut, style.faint(palette))
        line.addWidget(self.shortcut)


class SessionsPopup(controls.RoundedFrame):
    """The history under the toolbar's title; the dock confirms a deletion before it happens."""

    chosen = pyqtSignal(str)
    renamed = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str, str)
    new_requested = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(POPUP_RADIUS, parent)
        self._palette = palette
        try:
            flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        except TypeError:
            flags = None
        if flags is not None:
            self.setWindowFlags(flags)
        # A popup is a window of its own: it does not inherit the panel's palette, so it takes the theme's.
        style.apply_palette(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.set_look(style.surface(palette).name(), style.border_strong(palette).name())
        self.setFixedWidth(POPUP_WIDTH)
        column = QVBoxLayout(self)
        column.setContentsMargins(POPUP_PADDING, POPUP_PADDING, POPUP_PADDING, POPUP_PADDING)
        column.setSpacing(1)
        self.new_row = NewRow(palette)
        self.new_row.clicked.connect(self._new)
        column.addWidget(self.new_row)
        column.addWidget(controls.menu_rule(palette))
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The list wears the popup's own surface: a default viewport is the window grey.
        style.fill(self._area.viewport(), style.surface(palette))
        column.addWidget(self._area)
        self.rows: list[SessionRow] = []
        self._current = ""

    def show_sessions(self, entries: list[Entry], anchor: QWidget, now: float) -> None:
        """Fill the list and open it under `anchor`, left edges aligned."""
        holder = QWidget()
        style.fill(holder, style.surface(self._palette))
        rows = QVBoxLayout(holder)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(1)
        self.rows = []
        self._current = next((entry.identifier for entry in entries if entry.current), "")
        for label, items in day_groups(entries, now):
            rows.addWidget(controls.caption(label, self._palette))
            for entry, meta in items:
                row = SessionRow(entry, meta, self._palette)
                row.chosen.connect(self._choose)
                row.renamed.connect(self.renamed.emit)
                row.delete_requested.connect(self._delete)
                rows.addWidget(row)
                self.rows.append(row)
        if not entries:
            empty = controls.small(NO_SESSIONS, self._palette)
            empty.setContentsMargins(10, 6, 10, 8)
            rows.addWidget(empty)
        rows.addStretch(1)
        self._area.setWidget(holder)
        self._area.setFixedHeight(min(MAX_LIST_HEIGHT, holder.sizeHint().height()))
        self.adjustSize()
        corner = anchor.mapToGlobal(QPoint(0, anchor.height()))
        self.move(corner.x(), corner.y() + controls.MENU_GAP)
        self.show()

    def keyPressEvent(self, event: Any) -> None:
        if controls.is_new_shortcut(event):
            self._new()
            return
        super().keyPressEvent(event)

    def _new(self) -> None:
        self.hide()
        self.new_requested.emit()

    def _choose(self, identifier: str) -> None:
        self.hide()
        # The open conversation is already on screen: replaying it would only blink.
        if identifier != self._current:
            self.chosen.emit(identifier)

    def _delete(self, identifier: str, title: str) -> None:
        # Closed first: the confirmation is modal and a popup must not sit behind it.
        self.hide()
        self.delete_requested.emit(identifier, title)
