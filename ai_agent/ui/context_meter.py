"""The context meter under the composer, as in Claude Code: a ring, and a popup with the numbers.

The ring fills with the share of the model's window the latest request used. Its
popup shows the window, how far auto-compaction is, a button to compact now and
what this conversation has spent. Everything is painted, so updates are repaints.
"""

from typing import Any

from qgis.PyQt.QtCore import QPoint, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPen
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

RING = 16
RING_WIDTH = 2.0
BAR_HEIGHT = 5
POPUP_WIDTH = 380
POPUP_RADIUS = 12
# Matches the core's auto-compaction share: past it the ring turns to the warning colour.
FULL_SHARE = 0.9
TITLE = tr("Context window")
USED = "{0} / {1} ({2}%)"
UNTIL = tr("{0} until auto-compact")
COMPACT = tr("Compact")
SPENT = tr("Spent in this conversation")
SPENT_HINT = tr(
    "Every step of the agent is a separate request that sends the whole context again, "
    "so a conversation spends many times its window."
)
SPENT_REQUESTS = "{0} · {1}"
TOKENS = tr("{0} tokens")
RING_TIP = tr("Context window: {0}% used")


def tokens(value: int) -> str:
    """`950`, `21.3k`, `1M` — the way the numbers read in Claude Code."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    if value >= 1000:
        return f"{value / 1000:.1f}".removesuffix(".0") + "k"
    return str(max(0, value))


class ContextRing(QToolButton):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.share = 0.0
        self.setFixedSize(RING + 10, RING + 10)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setStyleSheet(
            "QToolButton { border: none; background: transparent; border-radius: 7px; }"
            f"QToolButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
        )

    def set_share(self, share: float) -> None:
        share = min(1.0, max(0.0, share))
        self.setToolTip(RING_TIP.format(round(share * 100)))
        if share != self.share:
            self.share = share
            self.update()

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = (self.width() - RING) / 2 + RING_WIDTH / 2
        box = QRectF(inset, inset, RING - RING_WIDTH, RING - RING_WIDTH)
        track = QPen(style.hairline(self._palette))
        track.setWidthF(RING_WIDTH)
        painter.setPen(track)
        painter.drawEllipse(box)
        if self.share > 0:
            colour = style.warning(self._palette) if self.share >= FULL_SHARE else style.accent(self._palette)
            arc = QPen(colour)
            arc.setWidthF(RING_WIDTH)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc)
            # Qt angles are sixteenths of a degree, counter-clockwise from three o'clock.
            painter.drawArc(box, 90 * 16, -int(self.share * 360 * 16))
        painter.end()


class UsageBar(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.share = 0.0
        self.setFixedHeight(BAR_HEIGHT)

    def set_share(self, share: float) -> None:
        self.share = min(1.0, max(0.0, share))
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = BAR_HEIGHT / 2
        painter.setBrush(style.card(self._palette))
        painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
        if self.share > 0:
            colour = style.warning(self._palette) if self.share >= FULL_SHARE else style.accent(self._palette)
            painter.setBrush(colour)
            painter.drawRoundedRect(
                QRectF(0, 0, max(BAR_HEIGHT, self.width() * self.share), BAR_HEIGHT), radius, radius
            )
        painter.end()


class ContextPopup(controls.RoundedFrame):
    compact_requested = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(POPUP_RADIUS, parent)
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
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(_muted(TITLE, palette))
        head.addStretch(1)
        self.used = _muted("", palette)
        head.addWidget(self.used)
        column.addLayout(head)
        self.bar = UsageBar(palette)
        column.addWidget(self.bar)
        action = QHBoxLayout()
        self.until = QLabel()
        self.until.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        action.addWidget(self.until)
        action.addStretch(1)
        self.compact = QPushButton(COMPACT)
        self.compact.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compact.setStyleSheet(fields.plain_button(palette))
        self.compact.clicked.connect(self._on_compact)
        action.addWidget(self.compact)
        column.addLayout(action)
        column.addWidget(fields.separator(palette))
        spent_line = QHBoxLayout()
        spent_caption = _muted(SPENT, palette)
        spent_caption.setToolTip(SPENT_HINT)
        spent_line.addWidget(spent_caption)
        spent_line.addStretch(1)
        self.spent = QLabel()
        self.spent.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        spent_line.addWidget(self.spent)
        column.addLayout(spent_line)

    def show_numbers(self, used: int, window: int, spent: int, until: int, turns: int = 0) -> None:
        share = used / window if window else 0.0
        self.used.setText(USED.format(tokens(used), tokens(window), round(share * 100)))
        self.bar.set_share(share)
        self.until.setText(UNTIL.format(tokens(max(0, until))))
        spent_text = TOKENS.format(tokens(spent))
        if turns:
            spent_text = SPENT_REQUESTS.format(spent_text, tr_n("%n request(s)", turns))
        self.spent.setText(spent_text)

    def open_above(self, anchor: QWidget) -> None:
        """Right edges aligned: the ring sits at the composer's right end."""
        self.adjustSize()
        corner = anchor.mapToGlobal(QPoint(anchor.width(), 0))
        self.move(corner.x() - self.width(), corner.y() - self.sizeHint().height() - controls.MENU_GAP)
        self.show()

    def _on_compact(self) -> None:
        self.hide()
        self.compact_requested.emit()


class ContextMeter(QWidget):
    """The ring and its popup, fed with the numbers by the dock."""

    compact_requested = pyqtSignal()

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        self.ring = ContextRing(palette)
        line.addWidget(self.ring)
        self.popup = ContextPopup(palette)
        self.popup.compact_requested.connect(self.compact_requested.emit)
        self.ring.clicked.connect(lambda: self.popup.open_above(self.ring))
        self.set_numbers(0, 0, 0)

    def set_numbers(self, used: int, window: int, spent: int, turns: int = 0) -> None:
        self.ring.set_share(used / window if window else 0.0)
        self.popup.show_numbers(used, window, spent, int(window * FULL_SHARE) - used, turns)


def _muted(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
    return label
