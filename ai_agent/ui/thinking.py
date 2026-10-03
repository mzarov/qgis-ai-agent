import time

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import style
from ai_agent.ui.disclosure import Disclosure

TEXT_FONT_SCALE = 0.9
REPAINT_INTERVAL_MS = 80
SHORTEST_SHOWN = 0.1
THINKING_TITLE = tr("Thinking…")
THOUGHT_TITLE = tr("Thought")


class ThinkingBlock(QFrame):
    """One row of an activity group: the model's reasoning under a fold line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self._header = Disclosure(palette)
        self._toggle = self._header.toggle
        self._title = self._header.title
        self._elapsed = self._header.detail
        self._header.toggled.connect(self._on_toggled)
        column.addWidget(self._header)
        column.addWidget(self._build_body(palette))
        self._text = ""
        self._started = time.monotonic()
        self._deliveries = 0
        self._finished = False
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(REPAINT_INTERVAL_MS)
        self._repaint.timeout.connect(self._render_text)
        self._toggle.setChecked(True)
        self._refresh()

    def _build_body(self, palette) -> QWidget:
        self._body_holder = QWidget()
        self._body_holder.setStyleSheet("border: none;")
        layout = QVBoxLayout(self._body_holder)
        layout.setContentsMargins(0, 0, 0, 2)
        self._body = QLabel()
        self._body.setTextFormat(Qt.TextFormat.PlainText)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._body.setStyleSheet(
            f"color: {style.css_color(style.muted(palette))};"
            f"border-left: 2px solid {style.css_color(style.hairline(palette))};"
            "border-radius: 0; padding: 1px 0 1px 10px;"
        )
        font = self._body.font()
        font.setItalic(True)
        self._body.setFont(font)
        _shrink(self._body)
        layout.addWidget(self._body)
        return self._body_holder

    def append(self, delta: str) -> None:
        self._text += delta
        self._deliveries += 1
        if self._deliveries == 1:
            self._render_text()
            self._refresh()
        elif not self._repaint.isActive():
            self._repaint.start()

    def _render_text(self) -> None:
        self._body.setText(self._text)

    @property
    def _watched_live(self) -> bool:
        return self._deliveries > 1

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._repaint.stop()
        self._render_text()
        self._toggle.setChecked(False)
        self._refresh()

    def _refresh(self) -> None:
        self._title.setText(THOUGHT_TITLE if self._finished else THINKING_TITLE)
        took = time.monotonic() - self._started
        # "0.0 s" claims a measurement that did not happen: reasoning that arrived in one burst.
        if self._finished and self._watched_live and took >= SHORTEST_SHOWN:
            self._header.set_detail(format_seconds(took))
        else:
            self._header.set_detail("")

    def _on_toggled(self, expanded: bool) -> None:
        self._body_holder.setVisible(expanded)


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return tr("{0} s").format(f"{seconds:.1f}")
    return tr("{0} min {1} s").format(int(seconds // 60), int(seconds % 60))


def _shrink(label: QLabel) -> None:
    font = label.font()
    font.setPointSizeF(max(1.0, font.pointSizeF() * TEXT_FONT_SCALE))
    label.setFont(font)
