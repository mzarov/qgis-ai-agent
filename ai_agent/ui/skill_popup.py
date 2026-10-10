from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style

MAX_ROWS = 8
POPUP_NAME = "skillPopup"
ROW_NAME = "skillRow"
POPUP_MARGINS = (6, 6, 6, 4)
ROW_MARGINS = (8, 6, 8, 6)
ICON_TILE = 26
ICON_SIZE = 15
ICON_RADIUS = 7
FOOTER_NAME = "popupFooter"
LAYER_PREFIX = "@"
KEY_CHOOSE = tr("choose")
KEY_INSERT = tr("insert")
KEY_CLOSE = tr("close")
ROW_GAP = 10
GAP_ABOVE_ANCHOR = 6
SELECTION_TINT = 0.22
ROW_RADIUS = 8
SKILL_PREFIX = "/"
DESCRIPTION_SCALE = 0.86
LOCAL_BADGE = tr("local")
EMPTY = tr("No matching skill")


def match_skills(query: str, items: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    needle = (query or "").strip().lower()
    prefixed = [item for item in items if item[0].lower().startswith(needle)]
    inside = [item for item in items if needle and needle in item[0].lower() and item not in prefixed]
    return (prefixed + inside)[:MAX_ROWS]


class SkillRow(controls.RoundedFrame):
    """One match; the selection is painted, so hovering never restyles the list mid-event."""

    clicked = pyqtSignal(str)
    hovered = pyqtSignal(str)

    def __init__(self, name: str):
        super().__init__(ROW_RADIUS)
        self.name = name
        self.setObjectName(ROW_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def mousePressEvent(self, event: Any) -> None:
        self.clicked.emit(self.name)

    def enterEvent(self, event: Any) -> None:
        self.hovered.emit(self.name)


class SkillPopup(controls.RoundedFrame):
    """The list above the composer. Its box is painted: a style sheet on it reset its rows' palette to
    QGIS's, and in a dark QGIS the light panel's names came out white on white."""

    chosen = pyqtSignal(str)

    def __init__(self, host: QWidget):
        super().__init__(style.CARD_RADIUS, host)
        self._host = host
        self._palette = host.palette()
        self._matches: list[tuple[str, str, str]] = []
        self._rows: list[controls.RoundedFrame] = []
        self._index = 0
        self._prefix = SKILL_PREFIX
        self.setObjectName(POPUP_NAME)
        self.set_look(style.panel(self._palette).name(), style.hairline(self._palette).name())
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(*POPUP_MARGINS)
        self._column.setSpacing(0)
        self._column.addWidget(self._footer())
        self.hide()

    def show_matches(
        self, query: str, items: list[tuple[str, str, str]], anchor: QWidget, prefix: str = SKILL_PREFIX
    ) -> None:
        self._prefix = prefix
        self._matches = match_skills(query, items)
        self._rebuild()
        self._index = 0
        self._paint_selection()
        self.adjustSize()
        self._place_above(anchor)
        self.show()
        self.raise_()

    def move_selection(self, delta: int) -> None:
        if not self._matches:
            return
        self._index = (self._index + delta) % len(self._matches)
        self._paint_selection()

    def current_name(self) -> str:
        if not self._matches:
            return ""
        return self._matches[self._index][0]

    def choose_current(self) -> bool:
        name = self.current_name()
        if not name:
            return False
        self.chosen.emit(name)
        return True

    def _rebuild(self) -> None:
        for row in self._rows:
            self._column.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._rows = []
        if not self._matches:
            empty = QLabel(EMPTY)
            empty.setContentsMargins(10, 5, 10, 5)
            style.ink(empty, style.muted(self._palette))
            self._rows.append(self._wrap(empty))
        for name, description, origin in self._matches:
            self._rows.append(self._row(name, description, origin))
        for row in self._rows:
            self._column.insertWidget(self._column.count() - 1, row)

    def _wrap(self, widget: QWidget) -> QFrame:
        frame = controls.RoundedFrame(ROW_RADIUS)
        frame.setObjectName(ROW_NAME)
        line = QHBoxLayout(frame)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(widget)
        return frame

    def _row(self, name: str, description: str, origin: str) -> QFrame:
        frame = SkillRow(name)
        frame.clicked.connect(self.chosen.emit)
        frame.hovered.connect(self._hover)
        line = QHBoxLayout(frame)
        line.setContentsMargins(*ROW_MARGINS)
        line.setSpacing(ROW_GAP)
        line.addWidget(self._icon_tile())
        title = QLabel(f"{self._prefix}{name}")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        style.ink(title, style.text(self._palette))
        line.addWidget(title)
        if origin == "local":
            line.addWidget(controls.badge(LOCAL_BADGE, "accent", self._palette))
        note = controls.ElidedLabel(description)
        style.scale_font(note, DESCRIPTION_SCALE)
        style.ink(note, style.muted(self._palette))
        line.addWidget(note, 1)
        return frame

    def _icon_tile(self) -> QLabel:
        role = "layer" if self._prefix == LAYER_PREFIX else "skills"
        return controls.icon_tile(role, self._palette, ICON_TILE, ICON_SIZE, ICON_RADIUS, self._prefix)

    def _footer(self) -> QWidget:
        """The key hints under a hairline; the line is a filled strip, not a border in a style sheet."""
        footer = QWidget()
        footer.setObjectName(FOOTER_NAME)
        column = QVBoxLayout(footer)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        rule = QWidget()
        rule.setFixedHeight(style.HAIRLINE)
        style.fill(rule, style.hairline(self._palette))
        column.addWidget(rule)
        keys = QWidget()
        column.addWidget(keys)
        line = QHBoxLayout(keys)
        line.setContentsMargins(8, 6, 8, 2)
        line.setSpacing(5)
        for keys, word in ((("↑", "↓"), KEY_CHOOSE), (("Tab",), KEY_INSERT), (("Esc",), KEY_CLOSE)):
            for key in keys:
                line.addWidget(controls.KeyCap(key, self._palette), 0, Qt.AlignmentFlag.AlignVCenter)
            label = controls.small(word, self._palette)
            label.setWordWrap(False)
            line.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
            line.addSpacing(8)
        line.addStretch(1)
        return footer

    def _hover(self, name: str) -> None:
        names = [match[0] for match in self._matches]
        if name in names:
            self._index = names.index(name)
            self._paint_selection()

    def _paint_selection(self) -> None:
        tint = style.blend(style.panel(self._palette), style.accent(self._palette), SELECTION_TINT)
        for index, row in enumerate(self._rows):
            selected = bool(self._matches) and index == self._index
            row.set_look(tint.name() if selected else None, None)

    def _place_above(self, anchor: QWidget) -> None:
        origin = anchor.mapTo(self._host, QPoint(0, 0))
        # The anchor's width, never the rows' wish: long descriptions elide instead of overflowing the dock.
        self.setFixedWidth(anchor.width())
        self.move(origin.x(), origin.y() - self.sizeHint().height() - GAP_ABOVE_ANCHOR)
