from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import settings_fields as fields
from ai_agent.ui import style

HEADING_SPACING = 5
GROUP_SPACING = 18
BLOCK_SPACING = 8
BLOCK_PADDING = 13
BLOCK_SIDE_PADDING = 15
TITLE_SCALE = 1.15
SUGGESTION_NAME = "suggestion"
SIDE_INSET = 4
NEEDS_KEY_TITLE = tr("One step before we start")
NEEDS_KEY_BODY = tr(
    "The agent talks to a language model of your choice, so it needs an address "
    "and a key — or nothing at all if you run a local model on localhost."
)
OPEN_SETTINGS = tr("Open settings")
READY_TITLE = tr("Ask in plain language")
# Users are everywhere: the one place named is one everybody knows.
SUGGESTIONS = (
    tr("What layers do I have and what is in them?"),
    tr("Colour the layer by category and add labels"),
    tr("Download cafés in Paris from OpenStreetMap"),
)


def welcome_content(configured: bool) -> tuple[str, str, tuple[str, ...]]:
    if configured:
        return READY_TITLE, "", SUGGESTIONS
    return NEEDS_KEY_TITLE, NEEDS_KEY_BODY, ()


class Suggestion(QFrame):
    """A clickable example request. A frame with a wrapping label, not a button: button text never
    wraps, so a long example was cut off in a narrow dock."""

    chosen = pyqtSignal(str)

    def __init__(self, text: str, palette: Any):
        super().__init__()
        self.text = text
        self.setObjectName(SUGGESTION_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#{SUGGESTION_NAME} {{ border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f" border-radius: {style.CARD_RADIUS}px; background: {style.css_color(style.card(palette))}; }}"
            f"QFrame#{SUGGESTION_NAME}:hover {{ border-color: {style.css_color(style.border_strong(palette))};"
            f" background: {style.css_color(style.elevated(palette))}; }}"
        )
        line = QVBoxLayout(self)
        line.setContentsMargins(BLOCK_SIDE_PADDING, BLOCK_PADDING, BLOCK_SIDE_PADDING, BLOCK_PADDING)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; background: transparent;")
        line.addWidget(label)

    def mousePressEvent(self, _event: Any) -> None:
        self.chosen.emit(self.text)


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
        if body:
            column.addWidget(_body(body, palette))
        column.addSpacing(GROUP_SPACING)
        for index, text in enumerate(suggestions):
            if index:
                column.addSpacing(BLOCK_SPACING)
            column.addWidget(self._suggestion(text, palette))
        if not suggestions:
            column.addWidget(self._settings_button(palette))
        column.addStretch(1)

    def _suggestion(self, text: str, palette: Any) -> QFrame:
        card = Suggestion(text, palette)
        card.chosen.connect(self.suggestion_chosen.emit)
        return card

    def _settings_button(self, palette: Any) -> QPushButton:
        button = QPushButton(OPEN_SETTINGS)
        button.setStyleSheet(fields.accent_button(palette))
        button.clicked.connect(self.settings_requested.emit)
        return button


def _title(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    style.scale_font(label, TITLE_SCALE, bold=True)
    label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; border: none;")
    return label


def _body(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
    return label
