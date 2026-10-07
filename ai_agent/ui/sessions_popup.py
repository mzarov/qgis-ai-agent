"""The conversations menu: pick a past conversation, rename it in place, or delete it.

Each row is the title, with a pencil and a bin on the right. The pencil turns the
title into an editor (Enter keeps, Esc drops); the bin closes the menu and asks the
dock to confirm, because deleting is for good. Rows paint their hover, so nothing
restyles while a mouse event runs.
"""

from typing import Any

from qgis.PyQt.QtCore import QPoint, QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLineEdit, QScrollArea, QToolButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

POPUP_WIDTH = 340
POPUP_RADIUS = 12
ROW_RADIUS = 8
MAX_LIST_HEIGHT = 420
ICON = 15
ICON_BUTTON = 24
RENAME = tr("Rename")
DELETE = tr("Delete")
NO_SESSIONS = tr("No past conversations")
TITLE = tr("Conversations")


class SessionRow(controls.RoundedFrame):
    chosen = pyqtSignal(str)
    renamed = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str, str)

    def __init__(self, identifier: str, title: str, palette: Any, parent: QWidget | None = None):
        super().__init__(ROW_RADIUS, parent)
        self.identifier = identifier
        self.title = title
        self._fill = style.card(palette).name()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 4, 4, 4)
        line.setSpacing(2)
        self.label = controls.ElidedLabel(title)
        self.label.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(self.label, 1)
        self.editor = QLineEdit(title)
        self.editor.setStyleSheet(fields.input_style(palette))
        self.editor.setVisible(False)
        self.editor.returnPressed.connect(self._keep_name)
        line.addWidget(self.editor, 1)
        self.rename_button = self._icon_button("rename", "✎", RENAME, palette)
        self.rename_button.clicked.connect(self.start_rename)
        line.addWidget(self.rename_button)
        self.delete_button = self._icon_button("delete", "🗑", DELETE, palette)
        self.delete_button.clicked.connect(self._ask_delete)
        line.addWidget(self.delete_button)
        self._show_actions(False)

    @staticmethod
    def _icon_button(role: str, fallback: str, tooltip: str, palette: Any) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(ICON_BUTTON, ICON_BUTTON)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 6px; }"
            f"QToolButton:hover {{ background: {style.css_color(style.elevated(palette))}; }}"
        )
        icon = icons.drawn(role, style.muted(palette), ICON)
        if icon is None:
            button.setText(fallback)
        else:
            button.setIcon(icon)
            button.setIconSize(QSize(ICON, ICON))
        return button

    def _show_actions(self, shown: bool) -> None:
        # Only the row under the pointer shows them; hidden ones keep their room, so titles do not jump.
        for button in (self.rename_button, self.delete_button):
            policy = button.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            button.setSizePolicy(policy)
            button.setVisible(shown)

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
        self.rename_button.setVisible(True)

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
        self.set_look(self._fill, None)
        self._show_actions(True)
        if self.editor.isVisible():
            self.rename_button.setVisible(False)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.set_look(None, None)
        if not self.editor.isVisible():
            self._show_actions(False)
        super().leaveEvent(event)


class SessionsPopup(controls.RoundedFrame):
    """Past conversations under the header button; the dock confirms a deletion before it happens."""

    chosen = pyqtSignal(str)
    renamed = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str, str)

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
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        self.setFixedWidth(POPUP_WIDTH)
        column = QVBoxLayout(self)
        column.setContentsMargins(6, 10, 6, 6)
        column.setSpacing(4)
        caption = controls.small(TITLE, palette)
        caption.setWordWrap(False)
        caption.setContentsMargins(10, 0, 0, 2)
        column.addWidget(caption)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The list wears the popup's own surface: a default viewport is the window grey.
        style.fill(self._area.viewport(), style.surface(palette))
        column.addWidget(self._area)
        self.rows: list[SessionRow] = []

    def show_sessions(self, sessions: list[tuple[str, str]], anchor: QWidget) -> None:
        """Fill the list and open it under `anchor`, right edges aligned (the button sits at the dock's right)."""
        holder = QWidget()
        style.fill(holder, style.surface(self._palette))
        rows = QVBoxLayout(holder)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        self.rows = []
        for identifier, title in sessions:
            row = SessionRow(identifier, title, self._palette)
            row.chosen.connect(self._choose)
            row.renamed.connect(self.renamed.emit)
            row.delete_requested.connect(self._delete)
            rows.addWidget(row)
            self.rows.append(row)
        if not sessions:
            empty = controls.small(NO_SESSIONS, self._palette)
            empty.setContentsMargins(10, 6, 10, 8)
            rows.addWidget(empty)
        rows.addStretch(1)
        self._area.setWidget(holder)
        self._area.setFixedHeight(min(MAX_LIST_HEIGHT, holder.sizeHint().height()))
        self.adjustSize()
        corner = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height()))
        self.move(corner.x() - self.width(), corner.y() + controls.MENU_GAP)
        self.show()

    def _choose(self, identifier: str) -> None:
        self.hide()
        self.chosen.emit(identifier)

    def _delete(self, identifier: str, title: str) -> None:
        # Closed first: the confirmation is modal and a popup must not sit behind it.
        self.hide()
        self.delete_requested.emit(identifier, title)
