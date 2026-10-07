"""The Personalisation page: who the user is, standing instructions, how they work and want answers, memory.

Everything here is stored on Save. The profile goes into the cached part of the
system prompt (`core/agent/profile_prompt.py`), so it costs nothing per turn;
the switches also steer the feed and the tools that move the map.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QLineEdit, QPlainTextEdit

from ai_agent.config import personal
from ai_agent.core.personal import save_user_notes
from ai_agent.core.settings import MAX_CUSTOM_INSTRUCTIONS, get_custom_instructions, set_custom_instructions
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.dropdown import Dropdown
from ai_agent.ui.memory_settings import MemoryNotes

TITLE = tr("Instructions for the agent")
INTRO = tr("Followed in every conversation: tone, units, naming, the rules of your organisation.")
PLACEHOLDER = tr(
    "For example: answer briefly. Use metres and EPSG:3857 for web maps. Name new layers in English with underscores."
)
WHO = tr("Who you are")
WHO_NOTE = tr("The agent reads this at the start of every conversation.")
NAME = tr("How to address you")
NAME_NOTE = tr("Used in answers. Empty: no name.")
NAME_PLACEHOLDER = tr("Your name")
ROLE = tr("Your work")
ROLE_NOTE = tr("A few words. It decides which data and methods come first.")
ROLE_PLACEHOLDER = tr("Hydrologist, urban planner…")
ABOUT = tr("About you")
ABOUT_NOTE = tr("What you work on, where and with which data.")
ABOUT_PLACEHOLDER = tr(
    "For example: hydrologist at a regional water agency; I mostly work with river basins and gauging "
    "stations in EPSG:32637."
)
HOW = tr("How you work")
EXPERIENCE = tr("GIS experience")
EXPERIENCE_NOTE = tr("How much the agent explains.")
UNITS = tr("Units")
UNITS_NOTE = tr("Kilometres and hectares, or miles and acres.")
LAYER_NAMES = tr("Layer names")
LAYER_NAMES_NOTE = tr("How the agent names the layers it creates.")
ANSWERS = tr("Answers")
LANGUAGE = tr("Answer language")
LANGUAGE_NOTE = tr("The language the agent writes in.")
SAME_AS_QGIS = tr("Same as QGIS")
STYLE = tr("Answer length")
STYLE_NOTE = tr("Short, balanced, or with the reasoning.")
QUESTIONS = tr("Questions")
QUESTIONS_NOTE = tr("How often the agent asks before acting.")
AUTO_ANSWER = tr("Answer questions for me after")
AUTO_ANSWER_NOTE = tr("The agent takes the answer it recommends and carries on.")
EXPLAIN = tr("Sum up after each run")
EXPLAIN_NOTE = tr("A short account of what changed.")
SHOW_STEPS = tr("Show steps while working")
SHOW_STEPS_NOTE = tr("Each call with what it found, above the answer.")
FOLLOW = tr("Move the map to the changes")
FOLLOW_NOTE = tr("The view follows new data and selections. Off keeps it where you left it.")
APPEARANCE = tr("Appearance")
PANEL_THEME = tr("Panel theme")
PANEL_THEME_NOTE = tr("Light or dark whatever the QGIS theme.")
MEMORY = tr("Memory")
MEMORY_NOTE = tr("Short facts about you that the agent keeps across conversations and projects.")
OWN_NOTES = tr("Let the agent add its own notes")
OWN_NOTES_NOTE = tr("When you mention something that will matter next time.")
CHOICE_TITLES = {
    "auto": tr("Auto"),
    "beginner": tr("Beginner"),
    "regular": tr("Regular"),
    "expert": tr("Expert"),
    "metric": tr("Metric"),
    "imperial": tr("Imperial"),
    "plain": tr("Plain words"),
    "technical": "snake_case",
    "concise": tr("Concise"),
    "balanced": tr("Balanced"),
    "detailed": tr("Detailed"),
    "rarely": tr("Rarely"),
    "when_needed": tr("When needed"),
    "often": tr("Often"),
}
# Languages under their names in the interface language, as system settings list them.
LANGUAGE_TITLES = {
    "en": tr("English"),
    "ru": tr("Russian"),
    "uk": tr("Ukrainian"),
    "de": tr("German"),
    "fr": tr("French"),
    "es": tr("Spanish"),
    "it": tr("Italian"),
    "pt": tr("Portuguese"),
    "pl": tr("Polish"),
    "nl": tr("Dutch"),
    "tr": tr("Turkish"),
    "zh": tr("Chinese"),
    "ja": tr("Japanese"),
}
THEME_TITLES = {"auto": tr("As in QGIS"), "light": tr("Light"), "dark": tr("Dark")}
AUTO_TITLES = {0: tr("Never"), 60: tr("1 min"), 180: tr("3 min"), 300: tr("5 min")}
COUNTER = "{0} / {1}"
ABOUT_HEIGHT = 110
EDITOR_HEIGHT = 132
EDITOR_GAP = 10
EDITOR_RADIUS = 8


class PersonalisationSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        self._palette = palette
        profile = personal.load()
        holder, column = fields.page()
        fields.section(column, WHO, palette, WHO_NOTE)
        self.name = self._line(profile.name, NAME_PLACEHOLDER, personal.MAX_NAME)
        self.role = self._line(profile.role, ROLE_PLACEHOLDER, personal.MAX_ROLE)
        fields.add_rows(
            column,
            palette,
            [fields.row(NAME, self.name, NAME_NOTE, palette), fields.row(ROLE, self.role, ROLE_NOTE, palette)],
        )
        fields.section(column, ABOUT, palette, ABOUT_NOTE)
        self.about, self.about_counter = self._text_area(
            column, profile.about, ABOUT_PLACEHOLDER, ABOUT_HEIGHT, personal.MAX_ABOUT
        )
        fields.section(column, TITLE, palette, INTRO)
        self.editor, self.counter = self._text_area(
            column, get_custom_instructions(), PLACEHOLDER, EDITOR_HEIGHT, MAX_CUSTOM_INSTRUCTIONS
        )
        fields.section(column, HOW, palette)
        self.experience = self._choice(personal.EXPERIENCE, profile.experience)
        self.units = self._choice(personal.UNITS, profile.units)
        self.layer_names = self._choice(personal.LAYER_NAMES, profile.layer_names)
        fields.add_rows(
            column,
            palette,
            [
                fields.custom_row(EXPERIENCE, self.experience, EXPERIENCE_NOTE, palette),
                fields.custom_row(UNITS, self.units, UNITS_NOTE, palette),
                fields.custom_row(LAYER_NAMES, self.layer_names, LAYER_NAMES_NOTE, palette),
            ],
        )
        fields.section(column, ANSWERS, palette)
        self.language = self._languages(profile.language)
        self.style = self._choice(personal.STYLES, profile.style)
        self.questions = self._choice(personal.QUESTIONS, profile.questions)
        self.auto_answer = self._choice(personal.AUTO_ANSWER, profile.auto_answer, AUTO_TITLES)
        self.explain = self._switch(profile.explain_after)
        self.show_steps = self._switch(profile.show_steps)
        self.follow = self._switch(profile.follow_changes)
        fields.add_rows(
            column,
            palette,
            [
                fields.custom_row(LANGUAGE, self.language, LANGUAGE_NOTE, palette),
                fields.custom_row(STYLE, self.style, STYLE_NOTE, palette),
                fields.custom_row(QUESTIONS, self.questions, QUESTIONS_NOTE, palette),
                fields.custom_row(AUTO_ANSWER, self.auto_answer, AUTO_ANSWER_NOTE, palette),
                fields.switch_row(EXPLAIN, self.explain, EXPLAIN_NOTE, palette),
                fields.switch_row(SHOW_STEPS, self.show_steps, SHOW_STEPS_NOTE, palette),
                fields.switch_row(FOLLOW, self.follow, FOLLOW_NOTE, palette),
            ],
        )
        fields.section(column, APPEARANCE, palette)
        self.panel_theme = self._choice(personal.PANEL_THEMES, profile.panel_theme, THEME_TITLES)
        fields.add_rows(column, palette, [fields.custom_row(PANEL_THEME, self.panel_theme, PANEL_THEME_NOTE, palette)])
        fields.section(column, MEMORY, palette, MEMORY_NOTE)
        self.memory = MemoryNotes(palette)
        self.memory.changed.connect(self.changed.emit)
        column.addWidget(self.memory.widget)
        self.own_notes = self._switch(profile.own_notes)
        column.addSpacing(EDITOR_GAP)
        fields.add_rows(column, palette, [fields.switch_row(OWN_NOTES, self.own_notes, OWN_NOTES_NOTE, palette)])
        column.addStretch(1)
        self.widget = holder

    def text(self) -> str:
        return self.editor.toPlainText().strip()[:MAX_CUSTOM_INSTRUCTIONS]

    def profile(self) -> personal.Profile:
        return personal.Profile(
            name=self.name.text().strip(),
            role=self.role.text().strip(),
            about=self.about.toPlainText().strip()[: personal.MAX_ABOUT],
            experience=self.experience.currentData(),
            units=self.units.currentData(),
            layer_names=self.layer_names.currentData(),
            language=self.language.currentData() or "",
            style=self.style.currentData(),
            questions=self.questions.currentData(),
            auto_answer=self.auto_answer.currentData(),
            explain_after=self.explain.isChecked(),
            show_steps=self.show_steps.isChecked(),
            follow_changes=self.follow.isChecked(),
            own_notes=self.own_notes.isChecked(),
            panel_theme=self.panel_theme.currentData(),
        )

    def save(self) -> None:
        """Store the page; ValueError when the notes could not be written."""
        personal.save(self.profile())
        set_custom_instructions(self.text())
        save_user_notes(self.memory.notes)

    def _line(self, text: str, placeholder: str, limit: int) -> QLineEdit:
        line = QLineEdit(text)
        line.setPlaceholderText(placeholder)
        line.setMaxLength(limit)
        line.textEdited.connect(lambda _text: self.changed.emit())
        return line

    def _choice(self, keys: tuple[Any, ...], current: Any, titles: dict[Any, str] | None = None) -> Any:
        choice = controls.Segmented(self._palette)
        for key in keys:
            choice.addItem((titles or CHOICE_TITLES).get(key, str(key)), key)
        choice.setCurrentIndex(max(0, choice.findData(current)))
        choice.currentIndexChanged.connect(lambda _index: self.changed.emit())
        return choice

    def _languages(self, current: str) -> Dropdown:
        combo = Dropdown(self._palette)
        combo.setFixedWidth(fields.CONTROL_WIDTH)
        combo.addItem(SAME_AS_QGIS, "")
        for code in personal.LANGUAGES:
            combo.addItem(LANGUAGE_TITLES.get(code, personal.LANGUAGES[code]), code)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        combo.currentIndexChanged.connect(lambda _index: self.changed.emit())
        return combo

    def _switch(self, checked: bool) -> Any:
        switch = fields.switch(self._palette)
        switch.setChecked(checked)
        switch.toggled.connect(lambda _on: self.changed.emit())
        return switch

    def _text_area(self, column: Any, text: str, placeholder: str, height: int, limit: int) -> tuple[Any, Any]:
        editor = QPlainTextEdit(text)
        editor.setPlaceholderText(placeholder)
        editor.setFixedHeight(height)
        palette = self._palette
        border = style.css_color(style.border_strong(palette))
        editor.setStyleSheet(
            f"QPlainTextEdit {{ background: {style.css_color(style.field(palette))};"
            f"color: {style.css_color(style.text(palette))}; border: {style.HAIRLINE}px solid {border};"
            f"border-radius: {EDITOR_RADIUS}px; padding: 6px; }}"
            f"QPlainTextEdit:focus {{ border: {style.HAIRLINE}px solid {style.css_color(style.accent(palette))}; }}"
        )
        counter = controls.small("", palette)
        counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        editor.textChanged.connect(lambda: self._count(editor, counter, limit))
        column.addSpacing(EDITOR_GAP)
        column.addWidget(editor)
        column.addSpacing(EDITOR_GAP)
        column.addWidget(counter)
        self._count(editor, counter, limit, emit=False)
        return editor, counter

    def _count(self, editor: Any, counter: Any, limit: int, emit: bool = True) -> None:
        length = len(editor.toPlainText().strip())
        counter.setText(COUNTER.format(length, limit))
        style.ink(counter, style.danger(self._palette) if length > limit else style.faint(self._palette))
        if emit:
            self.changed.emit()
