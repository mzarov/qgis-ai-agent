"""The Personalisation page: standing instructions the agent follows in every conversation."""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QPlainTextEdit

from ai_agent.core.settings import MAX_CUSTOM_INSTRUCTIONS, get_custom_instructions
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

TITLE = tr("Instructions for the agent")
INTRO = tr("Followed in every conversation: tone, units, naming, the rules of your organisation.")
PLACEHOLDER = tr(
    "For example: answer briefly. Use metres and EPSG:3857 for web maps. Name new layers in English with underscores."
)
COUNTER = "{0} / {1}"
EDITOR_HEIGHT = 132
EDITOR_GAP = 10
EDITOR_RADIUS = 8


class PersonalisationSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        holder, column = fields.page()
        fields.section(column, TITLE, palette, INTRO)
        self.editor = QPlainTextEdit(get_custom_instructions())
        self.editor.setPlaceholderText(PLACEHOLDER)
        self.editor.setFixedHeight(EDITOR_HEIGHT)
        border = style.css_color(style.border_strong(palette))
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background: {style.css_color(style.field(palette))};"
            f"color: {style.css_color(style.text(palette))}; border: {style.HAIRLINE}px solid {border};"
            f"border-radius: {EDITOR_RADIUS}px; padding: 6px; }}"
            f"QPlainTextEdit:focus {{ border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
        )
        self.editor.textChanged.connect(self._on_text)
        column.addSpacing(EDITOR_GAP)
        column.addWidget(self.editor)
        column.addSpacing(EDITOR_GAP)
        self.counter = controls.small("", palette)
        self.counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        column.addWidget(self.counter)
        column.addStretch(1)
        self._on_text(emit=False)
        self.widget = holder

    def text(self) -> str:
        return self.editor.toPlainText().strip()[:MAX_CUSTOM_INSTRUCTIONS]

    def _on_text(self, emit: bool = True) -> None:
        length = len(self.editor.toPlainText().strip())
        self.counter.setText(COUNTER.format(length, MAX_CUSTOM_INSTRUCTIONS))
        colour = (
            style.danger(self.counter.palette())
            if length > MAX_CUSTOM_INSTRUCTIONS
            else style.faint(self.counter.palette())
        )
        style.ink(self.counter, colour)
        if emit:
            self.changed.emit()
