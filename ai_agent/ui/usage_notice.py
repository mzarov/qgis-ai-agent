from collections.abc import Callable
from typing import Any

from qgis.core import Qgis
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QPushButton

from ai_agent.i18n import locale_code, tr
from ai_agent.ui.theme import MESSAGE_BAR_BORDER, MESSAGE_BAR_INK

TITLE = "AI Agent"
TEXT = tr("Sends anonymous daily usage counts — never what you write or your data.")
TURN_OFF = tr("Turn off")
DETAILS = tr("What is sent")
TURNED_OFF = tr("Usage statistics are off. Turn them back on in Settings → Privacy.")
STATS_PAGE = "https://mzarov.github.io/qgis-ai-agent/{0}usage-stats/"
DOC_LANGUAGES = ("ru",)
STAYS = 0
BUTTON_SHEET = (
    f"QPushButton {{ color: {MESSAGE_BAR_INK}; background: transparent; border: 1px solid {MESSAGE_BAR_BORDER};"
    " border-radius: 4px; padding: 3px 10px; }"
    " QPushButton:hover { background: rgba(37, 84, 161, 0.08); }"
)


def stats_page() -> str:
    language = locale_code()
    return STATS_PAGE.format(f"{language}/" if language in DOC_LANGUAGES else "")


class UsageNotice:
    def __init__(self, bar: Any, turn_off: Callable[[], None]) -> None:
        self._turn_off = turn_off
        self.item = bar.createMessage(TITLE, TEXT)
        self.details = QPushButton(DETAILS, self.item)
        self.details.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(stats_page())))
        self.off = QPushButton(TURN_OFF, self.item)
        self.off.clicked.connect(self._declined)
        for button in (self.details, self.off):
            button.setStyleSheet(BUTTON_SHEET)
            self.item.layout().addWidget(button)
        bar.pushWidget(self.item, Qgis.MessageLevel.Info, STAYS)

    def _declined(self) -> None:
        self._turn_off()
        # The item stays with the outcome on it: deleting it from its own button's click is unsafe.
        self.item.setText(TURNED_OFF)
        self.details.setVisible(False)
        self.off.setVisible(False)
