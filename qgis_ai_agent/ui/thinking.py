import time

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.ui import style

COLLAPSED = "›"
EXPANDED = "⌄"
MARKER_WIDTH = 14
BODY_INDENT = 26
TEXT_FONT_SCALE = 0.9
THINKING_TITLE = tr("Thinking…")
THOUGHT_TITLE = tr("Thought")


class ThinkingBlock(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet(
            f"QFrame {{ background: {style.css_color(style.card(palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header(palette))
        column.addWidget(self._build_body(palette))
        self._text = ""
        self._started = time.monotonic()
        self._deliveries = 0
        self._finished = False
        self._toggle.setChecked(True)
        self._refresh()

    def _build_header(self, palette) -> QWidget:
        header = QWidget()
        header.setStyleSheet("border: none;")
        row = QHBoxLayout(header)
        row.setContentsMargins(8, 6, 11, 6)
        row.setSpacing(8)

        self._toggle = QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._toggle.setFixedWidth(MARKER_WIDTH)
        self._toggle.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f"color: {style.css_color(style.muted(palette))}; font-size: 15px; }}"
        )
        self._toggle.toggled.connect(self._on_toggled)
        row.addWidget(self._toggle)

        self._title = QLabel()
        self._title.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        row.addWidget(self._title, 1)

        self._elapsed = QLabel()
        self._elapsed.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        _shrink(self._elapsed)
        row.addWidget(self._elapsed)
        return header

    def _build_body(self, palette) -> QWidget:
        self._body_holder = QWidget()
        self._body_holder.setStyleSheet("border: none;")
        layout = QVBoxLayout(self._body_holder)
        layout.setContentsMargins(BODY_INDENT, 0, 11, 9)
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._body.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        _shrink(self._body)
        layout.addWidget(self._body)
        return self._body_holder

    def append(self, delta: str) -> None:
        self._text += delta
        self._deliveries += 1
        self._body.setText(self._text)
        self._refresh()

    @property
    def _watched_live(self) -> bool:
        return self._deliveries > 1

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._toggle.setChecked(False)
        self._refresh()

    def _refresh(self) -> None:
        self._title.setText(THOUGHT_TITLE if self._finished else THINKING_TITLE)
        if self._finished and self._watched_live:
            self._elapsed.setText(format_seconds(time.monotonic() - self._started))
        else:
            self._elapsed.setText("")

    def _on_toggled(self, expanded: bool) -> None:
        self._toggle.setText(EXPANDED if expanded else COLLAPSED)
        self._body_holder.setVisible(expanded)


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return tr("{0} s").format(f"{seconds:.1f}")
    return tr("{0} min {1} s").format(int(seconds // 60), int(seconds % 60))


def _shrink(label: QLabel) -> None:
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * TEXT_FONT_SCALE))
    label.setFont(font)
