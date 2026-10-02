from typing import Any

from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style

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
SKILL_PREFIX = "/"
DESCRIPTION_SCALE = 0.86
LOCAL_BADGE = tr("local")
EMPTY = tr("No matching skill")


def match_skills(query: str, items: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    needle = (query or "").strip().lower()
    prefixed = [item for item in items if item[0].lower().startswith(needle)]
    inside = [item for item in items if needle and needle in item[0].lower() and item not in prefixed]
    return (prefixed + inside)[:MAX_ROWS]


class SkillRow(QFrame):
    clicked = pyqtSignal(str)
    hovered = pyqtSignal(str)

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.setObjectName(ROW_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def mousePressEvent(self, event: Any) -> None:
        self.clicked.emit(self.name)

    def enterEvent(self, event: Any) -> None:
        self.hovered.emit(self.name)


class SkillPopup(QFrame):
    chosen = pyqtSignal(str)

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._palette = host.palette()
        self._matches: list[tuple[str, str, str]] = []
        self._rows: list[QFrame] = []
        self._index = 0
        self._prefix = SKILL_PREFIX
        self.setObjectName(POPUP_NAME)
        self.setStyleSheet(
            f"QFrame#{POPUP_NAME} {{ background: {style.css_color(style.panel(self._palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(self._palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
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
            empty.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))}; padding: 5px 10px;")
            self._rows.append(self._wrap(empty))
        for name, description, origin in self._matches:
            self._rows.append(self._row(name, description, origin))
        for row in self._rows:
            self._column.insertWidget(self._column.count() - 1, row)

    def _wrap(self, widget: QWidget) -> QFrame:
        frame = QFrame()
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
        line.addWidget(title)
        if origin == "local":
            line.addWidget(controls.badge(LOCAL_BADGE, "accent", self._palette))
        note = controls.ElidedLabel(description)
        note_font = note.font()
        note_font.setPointSizeF(max(1.0, note_font.pointSizeF() * DESCRIPTION_SCALE))
        note.setFont(note_font)
        note.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))};")
        line.addWidget(note, 1)
        return frame

    def _icon_tile(self) -> QLabel:
        tile = QLabel()
        tile.setFixedSize(ICON_TILE, ICON_TILE)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setStyleSheet(
            f"QLabel {{ background: {style.css_color(style.card(self._palette))}; border-radius: {ICON_RADIUS}px; }}"
        )
        paint = icons.layer if self._prefix == LAYER_PREFIX else icons.skills
        try:
            tile.setPixmap(paint(style.muted(self._palette), ICON_SIZE).pixmap(ICON_SIZE, ICON_SIZE))
        except Exception:
            tile.setText(self._prefix)
        return tile

    def _footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName(FOOTER_NAME)
        footer.setStyleSheet(
            f"QFrame#{FOOTER_NAME} {{ border-top: {style.HAIRLINE}px solid"
            f" {style.css_color(style.hairline(self._palette))}; }}"
        )
        line = QHBoxLayout(footer)
        line.setContentsMargins(8, 6, 8, 2)
        line.setSpacing(5)
        for keys, word in ((("↑", "↓"), KEY_CHOOSE), (("Tab",), KEY_INSERT), (("Esc",), KEY_CLOSE)):
            for key in keys:
                line.addWidget(controls.keycap(key, self._palette))
            label = controls.small(word, self._palette)
            label.setWordWrap(False)
            line.addWidget(label)
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
            fill = style.css_color(tint) if selected else "transparent"
            row.setStyleSheet(f"QFrame#{ROW_NAME} {{ background: {fill}; border-radius: {style.CARD_RADIUS - 2}px; }}")

    def _place_above(self, anchor: QWidget) -> None:
        origin = anchor.mapTo(self._host, QPoint(0, 0))
        # The anchor's width, never the rows' wish: long descriptions elide instead of overflowing the dock.
        self.setFixedWidth(anchor.width())
        self.move(origin.x(), origin.y() - self.sizeHint().height() - GAP_ABOVE_ANCHOR)
