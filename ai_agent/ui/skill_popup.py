from qgis.PyQt.QtCore import QPoint, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import style

MAX_ROWS = 8
POPUP_NAME = "skillPopup"
ROW_NAME = "skillRow"
POPUP_MARGINS = (4, 4, 4, 4)
ROW_MARGINS = (10, 5, 10, 5)
ROW_GAP = 10
GAP_ABOVE_ANCHOR = 6
DESCRIPTION_SCALE = 0.86
LOCAL_BADGE = tr("local")
EMPTY = tr("No matching skill")


def match_skills(query: str, items: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    needle = (query or "").strip().lower()
    prefixed = [item for item in items if item[0].lower().startswith(needle)]
    inside = [item for item in items if needle and needle in item[0].lower() and item not in prefixed]
    return (prefixed + inside)[:MAX_ROWS]


class SkillPopup(QFrame):
    chosen = pyqtSignal(str)

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._palette = host.palette()
        self._matches: list[tuple[str, str, str]] = []
        self._rows: list[QFrame] = []
        self._index = 0
        self.setObjectName(POPUP_NAME)
        self.setStyleSheet(
            f"QFrame#{POPUP_NAME} {{ background: {style.css_color(style.panel(self._palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(self._palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(*POPUP_MARGINS)
        self._column.setSpacing(0)
        self.hide()

    def show_matches(self, query: str, items: list[tuple[str, str, str]], anchor: QWidget) -> None:
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
            row.deleteLater()
        self._rows = []
        if not self._matches:
            empty = QLabel(EMPTY)
            empty.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))}; padding: 5px 10px;")
            self._rows.append(self._wrap(empty))
        for name, description, origin in self._matches:
            self._rows.append(self._row(name, description, origin))
        for row in self._rows:
            self._column.addWidget(row)

    def _wrap(self, widget: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName(ROW_NAME)
        line = QHBoxLayout(frame)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(widget)
        return frame

    def _row(self, name: str, description: str, origin: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(ROW_NAME)
        line = QHBoxLayout(frame)
        line.setContentsMargins(*ROW_MARGINS)
        line.setSpacing(ROW_GAP)
        title = QLabel(f"/{name}")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        line.addWidget(title)
        if origin == "local":
            badge = QLabel(LOCAL_BADGE)
            badge.setStyleSheet(f"color: {style.css_color(style.accent(self._palette))};")
            line.addWidget(badge)
        note = QLabel(description)
        note_font = note.font()
        note_font.setPointSizeF(max(1.0, note_font.pointSizeF() * DESCRIPTION_SCALE))
        note.setFont(note_font)
        note.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))};")
        line.addWidget(note, 1)
        return frame

    def _paint_selection(self) -> None:
        for index, row in enumerate(self._rows):
            selected = bool(self._matches) and index == self._index
            fill = style.css_color(style.card(self._palette)) if selected else "transparent"
            row.setStyleSheet(f"QFrame#{ROW_NAME} {{ background: {fill}; border-radius: {style.CARD_RADIUS - 2}px; }}")

    def _place_above(self, anchor: QWidget) -> None:
        origin = anchor.mapTo(self._host, QPoint(0, 0))
        self.setFixedWidth(max(anchor.width(), self.sizeHint().width()))
        self.move(origin.x(), origin.y() - self.sizeHint().height() - GAP_ABOVE_ANCHOR)
