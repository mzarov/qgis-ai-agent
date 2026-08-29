from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.ui import settings_fields as fields
from qgis_ai_agent.ui import style

HEADING_SPACING = 5
GROUP_SPACING = 18
BLOCK_SPACING = 8
BLOCK_PADDING = 13
BLOCK_SIDE_PADDING = 15
TITLE_SCALE = 1.15
SIDE_INSET = 4
NEEDS_KEY_TITLE = tr("One step before we start")
NEEDS_KEY_BODY = tr(
    "The agent talks to a language model of your choice, so it needs an address "
    "and a key — or nothing at all if you run a local model on localhost."
)
OPEN_SETTINGS = tr("Open settings")
READY_TITLE = tr("Ask in plain language")
READY_BODY = tr("The agent reads the project itself. Nothing changes until you press Apply.")
SUGGESTIONS = (
    tr("What layers do I have and what is in them?"),
    tr("Colour the layer by its type and label the features"),
    tr("Download the cafes in Tver from OpenStreetMap"),
)


def welcome_content(configured: bool) -> tuple[str, str, tuple[str, ...]]:
    if configured:
        return READY_TITLE, READY_BODY, SUGGESTIONS
    return NEEDS_KEY_TITLE, NEEDS_KEY_BODY, ()


class WelcomeCard(QWidget):
    suggestion_chosen = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, configured: bool, parent: Any = None):
        super().__init__(parent)
        palette = self.palette()
        title, body, suggestions = welcome_content(configured)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        column = QVBoxLayout(self)
        column.setContentsMargins(SIDE_INSET, 0, SIDE_INSET, 0)
        column.setSpacing(HEADING_SPACING)
        column.addStretch(1)
        column.addWidget(_title(title, palette))
        column.addWidget(_body(body, palette))
        column.addSpacing(GROUP_SPACING)
        for index, text in enumerate(suggestions):
            if index:
                column.addSpacing(BLOCK_SPACING)
            column.addWidget(self._suggestion(text, palette))
        if not suggestions:
            column.addWidget(self._settings_button(palette))
        column.addStretch(1)

    def _suggestion(self, text: str, palette: Any) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ text-align: left;"
            f" padding: {BLOCK_PADDING}px {BLOCK_SIDE_PADDING}px;"
            f" border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f" border-radius: {style.CARD_RADIUS}px;"
            f" background: {style.css_color(style.card(palette))};"
            f" color: {style.css_color(style.text(palette))}; }}"
            f"QPushButton:hover {{ border-color: {style.css_color(style.accent(palette))};"
            f" background: {style.css_color(style.elevated(palette))}; }}"
        )
        button.clicked.connect(lambda: self.suggestion_chosen.emit(text))
        return button

    def _settings_button(self, palette: Any) -> QPushButton:
        button = QPushButton(OPEN_SETTINGS)
        button.setStyleSheet(fields.accent_button(palette))
        button.clicked.connect(self.settings_requested.emit)
        return button


def _title(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    font = label.font()
    font.setBold(True)
    font.setPointSizeF(max(1.0, font.pointSizeF() * TITLE_SCALE))
    label.setFont(font)
    label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; border: none;")
    return label


def _body(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
    return label
