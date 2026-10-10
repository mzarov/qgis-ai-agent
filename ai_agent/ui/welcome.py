"""The empty conversation: the compass arriving, what the agent is, the project, examples to start with.

Centred like the design's welcome: the mark plays its arrival once, a title,
one sentence on the deal (your model, your keys, nothing changes without you),
a line naming the open project, then full-width examples to start with. A click on
one sends it. Without a configured model the card asks for settings instead.
"""

from typing import Any

from qgis.PyQt.QtCore import QRect, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import compass, controls, icons, style, transitions
from ai_agent.ui import settings_fields as fields

STACK_GAP = 10
GROUP_GAP = 18
SUGGESTION_GAP = 6
SUGGESTION_PADDING = (12, 9, 12, 9)
SUGGESTION_RADIUS = 6
SUGGESTION_ICON = 16
PROJECT_ICON = 14
TITLE_SCALE = 17 / 13
SMALL = 0.92
SUGGESTION_NAME = "suggestion"
SIDE_INSET = 0
MARK = 56
NEEDS_KEY_TITLE = tr("One step before we start")
NEEDS_KEY_BODY = tr(
    "The agent talks to a language model of your choice, so it needs an address "
    "and a key — or nothing at all if you run a local model on localhost."
)
OPEN_SETTINGS = tr("Open settings")
READY_TITLE = tr("Ask about your map")
READY_BODY = tr("Your model, your keys, your project. Nothing changes without your approval.")
SAVED = tr("Previous conversation saved in history")
OPEN = tr("Open")
SAVED_ICON = 12
# Each example wears the icon of what it does: read, style, imagery, measure.
SUGGESTIONS = (
    ("layer", tr("Which layers are in the project and what is in them?")),
    ("style", tr("Colour the districts by population")),
    ("image", tr("Find a cloud-free satellite image of the current extent from this summer")),
    ("measure", tr("Calculate the built-up area in each district")),
)


def welcome_content(configured: bool) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    if configured:
        return READY_TITLE, READY_BODY, SUGGESTIONS
    return NEEDS_KEY_TITLE, NEEDS_KEY_BODY, ()


class Suggestion(QFrame):
    """A clickable example request. A frame with a wrapping label, not a button: button text never
    wraps, so a long example was cut off in a narrow dock."""

    chosen = pyqtSignal(str)

    def __init__(self, role: str, text: str, palette: Any):
        super().__init__()
        self.text = text
        self.setObjectName(SUGGESTION_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#{SUGGESTION_NAME} {{ border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f" border-radius: {SUGGESTION_RADIUS}px; background: {style.css_color(style.surface(palette))}; }}"
            f"QFrame#{SUGGESTION_NAME}:hover {{ border-color: {style.css_color(style.border_strong(palette))};"
            f" background: {style.css_color(style.card(palette))}; }}"
        )
        line = QHBoxLayout(self)
        line.setContentsMargins(*SUGGESTION_PADDING)
        line.setSpacing(10)
        glyph = QLabel()
        glyph.setFixedSize(SUGGESTION_ICON, SUGGESTION_ICON)
        glyph.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        icon = icons.drawn(role, style.faint(palette), SUGGESTION_ICON)
        if icon is not None:
            glyph.setPixmap(icon.pixmap(SUGGESTION_ICON, SUGGESTION_ICON))
        line.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; background: transparent;")
        line.addWidget(label, 1)

    def mousePressEvent(self, _event: Any) -> None:
        self.chosen.emit(self.text)


class WelcomeCard(QWidget):
    suggestion_chosen = pyqtSignal(str)
    settings_requested = pyqtSignal()
    history_requested = pyqtSignal()

    def __init__(self, configured: bool, project: str = "", parent: Any = None):
        super().__init__(parent)
        palette = self.palette()
        title, body, suggestions = welcome_content(configured)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        column = QVBoxLayout(self)
        column.setContentsMargins(SIDE_INSET, 0, SIDE_INSET, 0)
        column.setSpacing(STACK_GAP)
        column.addStretch(1)
        # The compass arrives: its needle swings in and settles at rest, once, when the welcome appears.
        self.mark = compass.Compass(MARK, palette)
        column.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignHCenter)
        self.mark.set_state(compass.ARRIVE)
        column.addWidget(_title(title, palette))
        if body:
            # Full width with centred text: an alignment flag would size a wrapping label by its hint and cut it.
            column.addWidget(_body(body, palette))
        self._configured = configured
        self.project = _project_line(palette)
        column.addWidget(self.project, 0, Qt.AlignmentFlag.AlignHCenter)
        self.set_project(project)
        column.addSpacing(GROUP_GAP - STACK_GAP)
        stack = QVBoxLayout()
        stack.setSpacing(SUGGESTION_GAP)
        for role, text in suggestions:
            stack.addWidget(self._suggestion(role, text, palette))
        column.addLayout(stack)
        if not suggestions:
            column.addWidget(self._settings_button(palette))
        # After "New conversation": where the previous one went, and a way back to it.
        self.saved = self._saved_line(palette)
        self.saved.setVisible(False)
        self._arrival: transitions.Arrival | None = None
        column.addWidget(self.saved, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)

    def set_project(self, text: str) -> None:
        self.project.label.setText(text)
        self.project.label.setToolTip(text)
        self.project.setVisible(bool(text) and self._configured)

    def show_saved(self) -> None:
        self.saved.setVisible(True)

    def prepare_arrival(self) -> None:
        """Wait unseen until `arrive` (the old conversation is still leaving)."""
        self._arrival = transitions.Arrival(self, self._saved_rect)

    def arrive(self) -> None:
        """Fade in and settle from below, the saved line a little behind, while the compass arrives."""
        if self._arrival is None:
            return
        self.mark.set_state(compass.ARRIVE)
        self._arrival.start()
        self._arrival = None

    def _saved_rect(self) -> QRect | None:
        return self.saved.geometry() if not self.saved.isHidden() else None

    def _saved_line(self, palette: Any) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(controls.glyph("saved", style.faint(palette), SAVED_ICON))
        text = QLabel(SAVED)
        style.scale_font(text, SMALL)
        style.ink(text, style.faint(palette))
        line.addWidget(text)
        link = QPushButton(OPEN)
        style.scale_font(link, SMALL)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.setFlat(True)
        link.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; padding: 0 2px;"
            f" color: {style.css_color(style.accent(palette))}; }}"
            f"QPushButton:hover {{ color: {style.css_color(style.accent_hover(palette))}; }}"
        )
        link.clicked.connect(self.history_requested.emit)
        line.addWidget(link)
        return holder

    def _suggestion(self, role: str, text: str, palette: Any) -> QFrame:
        card = Suggestion(role, text, palette)
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
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    style.scale_font(label, TITLE_SCALE, bold=True)
    label.setStyleSheet(f"color: {style.css_color(style.text(palette))}; border: none;")
    return label


def _body(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    label.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
    return label


def _project_line(palette: Any) -> QWidget:
    """The open project in one quiet line: its file, how many layers, the CRS; a long name elides."""
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    glyph = QLabel()
    icon = icons.drawn("layer", style.faint(palette), PROJECT_ICON)
    if icon is not None:
        glyph.setPixmap(icon.pixmap(PROJECT_ICON, PROJECT_ICON))
    line.addWidget(glyph)
    label = controls.ElidedLabel()
    # Sized by its text while there is room, so the centred line is as wide as it reads; elides below that.
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    style.scale_font(label, SMALL)
    style.ink(label, style.faint(palette))
    holder.label = label
    line.addWidget(label)
    return holder
