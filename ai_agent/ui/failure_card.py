"""A failed run in the feed: what happened in a few words, one sentence on what to do, Retry and Connection.

The model's request failing is not a remark in the margin but the end of the
turn, so it is a card like the plan's: an icon on a soft danger tile naming the
kind of failure (no connection, a refused key, a busy model…), the title, the
sentence, the server's own words in one quiet monospace line, and the buttons.
The first button shown is the outlined one; the second is a link.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.llm.failure_kinds import AUTH, BUSY, CONNECTION, NOT_FOUND, SETUP, TIMEOUT
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style

CARD_NAME = "failureCard"
CARD_RADIUS = 8
CARD_MARGINS = (12, 10, 12, 10)
TILE = 28
GLYPH = 16
BUTTON_HEIGHT = 26
TECHNICAL_SCALE = 11 / 13
RETRY = tr("Retry")
CONNECTION_PAGE = tr("Connection")
# The glyph by the kind of failure; any other kind wears the plain alert.
GLYPHS = {
    CONNECTION: "unplugged",
    SETUP: "connection",
    NOT_FOUND: "connection",
    AUTH: "key",
    BUSY: "busy",
    TIMEOUT: "late",
}
ALERT = "alert"
FALLBACK_MARK = "!"


class FailureCard(controls.RoundedFrame):
    retry_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(
        self,
        title: str,
        detail: str,
        message: str,
        kind: str,
        fixed_in_settings: bool,
        retryable: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(CARD_RADIUS, parent)
        palette = self.palette()
        self.setObjectName(CARD_NAME)
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        line = QHBoxLayout(self)
        line.setContentsMargins(*CARD_MARGINS)
        line.setSpacing(10)
        line.addWidget(_tile(GLYPHS.get(kind, ALERT), palette), 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(2)
        # In the card before anything joins it: a widget shown while still an orphan opens as a window.
        line.addLayout(column, 1)
        self.title = QLabel(title)
        self.title.setWordWrap(True)
        style.scale_font(self.title, 1.0, bold=True)
        style.ink(self.title, style.text(palette))
        column.addWidget(self.title)
        self.detail = controls.small(detail, palette)
        style.ink(self.detail, style.muted(palette))
        column.addWidget(self.detail)
        # What the server itself said, for whoever asks for help with it; the whole of it on hover.
        self.technical = controls.ElidedLabel(" ".join(message.split()))
        self.technical.setToolTip(message)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSizeF(max(1.0, self.font().pointSizeF() * TECHNICAL_SCALE))
        self.technical.setFont(mono)
        style.ink(self.technical, style.faint(palette))
        column.addWidget(self.technical)
        self.technical.setVisible(bool(message.strip()) and message.strip() != detail.strip())
        self._actions = QWidget()
        buttons = QHBoxLayout(self._actions)
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(6)
        self.retry = QPushButton(RETRY)
        self.retry.setFixedHeight(BUTTON_HEIGHT)
        self.retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry.clicked.connect(self.retry_requested.emit)
        buttons.addWidget(self.retry)
        self.settings = QPushButton(CONNECTION_PAGE)
        self.settings.setFixedHeight(BUTTON_HEIGHT)
        self.settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings.clicked.connect(self.settings_requested.emit)
        buttons.addWidget(self.settings)
        buttons.addStretch(1)
        column.addWidget(self._actions)
        self.settings.setVisible(fixed_in_settings)
        self._palette = palette
        self._show_retry(retryable)

    def plain_text(self) -> str:
        return f"{self.title.text()} {self.detail.text()}"

    def offer_retry(self) -> None:
        """The settings changed since: the same request may go through now."""
        self._show_retry(True)

    def retire(self) -> None:
        """The request moved on — replaced by a new one: Retry would send something stale."""
        self._show_retry(False)

    def _show_retry(self, shown: bool) -> None:
        self.retry.setVisible(shown)
        self._actions.setVisible(shown or not self.settings.isHidden())
        # The first action is the outlined button, a second one a link beside it.
        self.retry.setStyleSheet(_plain_button(self._palette))
        self.settings.setStyleSheet(_link_button(self._palette) if shown else _plain_button(self._palette))


def _tile(role: str, palette: Any) -> QLabel:
    tile = QLabel()
    tile.setFixedSize(TILE, TILE)
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    danger = style.danger(palette)
    tile.setStyleSheet(
        f"QLabel {{ background: {style.css_color(style.soft(palette, danger))}; border-radius: {TILE // 2}px; }}"
    )
    glyph = icons.drawn(role, danger, GLYPH)
    if glyph is not None:
        tile.setPixmap(glyph.pixmap(GLYPH, GLYPH))
    else:
        tile.setText(FALLBACK_MARK)
        tile.setStyleSheet(tile.styleSheet() + f"QLabel {{ color: {style.css_color(danger)}; }}")
    return tile


def _plain_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: {style.css_color(style.surface(palette))};"
        f" color: {style.css_color(style.text(palette))};"
        f" border: {style.HAIRLINE}px solid {style.css_color(style.border_strong(palette))};"
        " border-radius: 6px; padding: 0 12px; }"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
    )


def _link_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {style.css_color(style.accent(palette))};"
        " padding: 0 6px; border-radius: 4px; }"
        f"QPushButton:hover {{ background: {style.css_color(style.soft(palette, style.accent(palette)))}; }}"
    )
