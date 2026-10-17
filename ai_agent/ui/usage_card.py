"""The one-time question in the feed: share anonymous usage counts?

Asked once, after an answer, and only once the collector exists. The person
decides here or later in Settings → Privacy; until then nothing is counted.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui.failure_card import BUTTON_HEIGHT, CARD_MARGINS, CARD_RADIUS, link_button, plain_button

CARD_NAME = "usageCard"
STATS_PAGE = "https://mzarov.github.io/qgis-ai-agent/usage-stats/"
TITLE = tr("Help improve AI Agent?")
DETAIL = tr(
    "Once a day the plugin can send anonymous counts: how many runs and applies, which tools and "
    "skills ran, which errors happened, and the plugin and QGIS versions. Never what you wrote, the "
    "answers, your data or places. The totals are public."
)
WHAT_IS_SENT = tr("What is sent and the public totals")
SHARE = tr("Share counts")
DECLINE = tr("No thanks")
SHARED = tr("Thank you. Change it any time in Settings → Privacy.")
DECLINED = tr("Nothing is sent. Change it any time in Settings → Privacy.")


class UsageCard(controls.RoundedFrame):
    chosen = pyqtSignal(bool)

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(CARD_RADIUS, parent)
        self.setObjectName(CARD_NAME)
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        column = QVBoxLayout(self)
        column.setContentsMargins(*CARD_MARGINS)
        column.setSpacing(4)
        self.title = QLabel(TITLE)
        self.title.setWordWrap(True)
        style.scale_font(self.title, 1.0, bold=True)
        style.ink(self.title, style.text(palette))
        column.addWidget(self.title)
        self.detail = controls.small(DETAIL, palette)
        self.detail.setWordWrap(True)
        style.ink(self.detail, style.muted(palette))
        column.addWidget(self.detail)
        self.link = controls.small(f'<a href="{STATS_PAGE}">{WHAT_IS_SENT}</a>', palette)
        self.link.setTextFormat(Qt.TextFormat.RichText)
        self.link.setOpenExternalLinks(True)
        column.addWidget(self.link)
        self._actions = QWidget()
        buttons = QHBoxLayout(self._actions)
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(6)
        self.share = QPushButton(SHARE)
        self.decline = QPushButton(DECLINE)
        for button, sheet in ((self.share, plain_button(palette)), (self.decline, link_button(palette))):
            button.setFixedHeight(BUTTON_HEIGHT)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(sheet)
            buttons.addWidget(button)
        buttons.addStretch(1)
        column.addWidget(self._actions)
        self.share.clicked.connect(lambda: self._choose(True))
        self.decline.clicked.connect(lambda: self._choose(False))

    def plain_text(self) -> str:
        return f"{self.title.text()} {self.detail.text()}"

    def _choose(self, agreed: bool) -> None:
        self._actions.setVisible(False)
        self.detail.setText(SHARED if agreed else DECLINED)
        self.chosen.emit(agreed)
