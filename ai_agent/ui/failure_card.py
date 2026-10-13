"""A failed run in the feed: what happened in a few words, one sentence on what to do, Retry and Connection.

The model's request failing is not a remark in the margin but the end of the
turn, so it is a card like the plan's: an icon on a soft danger tile naming the
kind of failure (no connection, a refused key, a busy model…), the title, the
sentence, and the buttons. The exact technical text stays one hover away.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
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
        # The words the model and the log got, for whoever wants them: the card itself says it plainly.
        self.setToolTip(message)
        line = QHBoxLayout(self)
        line.setContentsMargins(*CARD_MARGINS)
        line.setSpacing(10)
        line.addWidget(_tile(GLYPHS.get(kind, ALERT), palette), 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(2)
        self.title = QLabel(title)
        self.title.setWordWrap(True)
        style.scale_font(self.title, 1.0, bold=True)
        style.ink(self.title, style.text(palette))
        column.addWidget(self.title)
        self.detail = controls.small(detail, palette)
        style.ink(self.detail, style.muted(palette))
        column.addWidget(self.detail)
        # Parented now: the column joins the card only at the end, and showing an orphan opens a window.
        self._actions = QWidget(self)
        buttons = QHBoxLayout(self._actions)
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(6)
        self.retry = QPushButton(RETRY)
        self.retry.setFixedHeight(BUTTON_HEIGHT)
        self.retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry.setStyleSheet(_plain_button(palette))
        self.retry.clicked.connect(self._retry)
        buttons.addWidget(self.retry)
        self.settings = QPushButton(CONNECTION_PAGE)
        self.settings.setFixedHeight(BUTTON_HEIGHT)
        self.settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings.setStyleSheet(_link_button(palette))
        self.settings.clicked.connect(self.settings_requested.emit)
        buttons.addWidget(self.settings)
        buttons.addStretch(1)
        column.addWidget(self._actions)
        self.retry.setVisible(retryable)
        self.settings.setVisible(fixed_in_settings)
        self._actions.setVisible(retryable or fixed_in_settings)
        line.addLayout(column, 1)

    def plain_text(self) -> str:
        return f"{self.title.text()} {self.detail.text()}"

    def retire(self) -> None:
        """The request moved on — sent again or replaced: Retry would send something stale."""
        self.retry.setVisible(False)
        self._actions.setVisible(not self.settings.isHidden())

    def _retry(self) -> None:
        self.retire()
        self.retry_requested.emit()


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
