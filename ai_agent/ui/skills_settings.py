from typing import Any

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.local_skills import describe_local_skills, skill_choices, write_example_skill
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

TITLE = tr("Your skills")
INTRO = tr(
    "A skill is a folder with a SKILL.md inside: a name, one line saying when to use it, and the rules in "
    "Markdown. Type / in the chat to invoke one; the agent can also load it by itself when the task fits."
)
OPEN_FOLDER = tr("Open folder")
CREATE_EXAMPLE = tr("Create an example")
NONE_YET = tr("No local skills yet — create the example and edit it.")
FOLDER_UNAVAILABLE = tr("The skills folder is unavailable in this QGIS profile.")
TOOLS_LINE = tr("Tools: {0}")
BUILT_IN = tr("Built in")
BUTTON_GAP = 8
GRID_COLUMNS = 3
GRID_GAP = 8
SKILL_NAME = "skillTile"
PATH_NAME = "skillsPath"


class SkillsSettings:
    def __init__(self, palette: Any):
        self._palette = palette
        holder, self._column = fields.page()
        fields.page_header(self._column, tr("Skills"), INTRO, palette)
        fields.section(self._column, TITLE, palette)
        self._column.addWidget(self._folder_strip(palette))
        self._column.addSpacing(GRID_GAP)
        self._list: QWidget = QWidget()
        self._list_index = self._column.count()
        self._column.addWidget(self._list)
        fields.section(self._column, BUILT_IN, palette)
        self._column.addWidget(self._built_in(palette))
        self._column.addStretch(1)
        self.widget: QWidget = holder
        self.refresh()

    def refresh(self) -> None:
        described = describe_local_skills()
        self._path.setText(described["path"] or FOLDER_UNAVAILABLE)
        self._path.setToolTip(described["path"] or "")
        fresh = QWidget()
        column = QVBoxLayout(fresh)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(fields.FIELD_SPACING + 4)
        tiles = [
            self._tile(f"/{entry['name']}", entry["description"], self._tools(entry), True)
            for entry in described["skills"]
        ]
        if tiles:
            column.addWidget(_grid(tiles))
        else:
            column.addWidget(fields.hint(NONE_YET, self._palette))
        for problem in described["problems"]:
            warning = fields.hint(problem, self._palette)
            warning.setStyleSheet(f"color: {style.css_color(style.danger(self._palette))};")
            column.addWidget(warning)
        self._column.insertWidget(self._list_index, fresh)
        self._list.hide()
        self._list.deleteLater()
        self._list = fresh

    def _folder_strip(self, palette: Any) -> QFrame:
        strip = QFrame()
        strip.setObjectName(PATH_NAME)
        strip.setStyleSheet(
            f"QFrame#{PATH_NAME} {{ background: {style.css_color(style.card(palette))};"
            f"border-radius: {fields.BUTTON_RADIUS}px; }}"
        )
        line = QHBoxLayout(strip)
        line.setContentsMargins(12, 8, 8, 8)
        line.setSpacing(BUTTON_GAP)
        # A profile path is long; it elides in the middle so both ends stay readable and the page keeps its width.
        self._path = controls.ElidedLabel("", mode=Qt.TextElideMode.ElideMiddle)
        self._path.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        line.addWidget(self._path, 1)
        open_button = QPushButton(OPEN_FOLDER)
        open_button.setStyleSheet(fields.plain_button(palette))
        open_button.clicked.connect(self._open_folder)
        line.addWidget(open_button)
        example_button = QPushButton(CREATE_EXAMPLE)
        example_button.setStyleSheet(fields.accent_button(palette))
        example_button.clicked.connect(self._create_example)
        line.addWidget(example_button)
        return strip

    def _built_in(self, palette: Any) -> QWidget:
        # Built-in descriptions are written for the model, in English; the tile shows the name
        # and keeps the description for the tooltip, so a translated window stays translated.
        choices = [choice for choice in skill_choices() if choice[2] != "local"]
        return _grid([self._tile(name, "", description, False) for name, description, _origin in choices])

    def _tile(self, name: str, description: str, tooltip: str, local: bool) -> QFrame:
        tile = QFrame()
        tile.setObjectName(SKILL_NAME)
        border = "dashed" if local else "solid"
        tile.setStyleSheet(
            f"QFrame#{SKILL_NAME} {{ background: {style.css_color(style.panel(self._palette))};"
            f"border: {style.HAIRLINE}px {border} {style.css_color(style.hairline(self._palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        column = QVBoxLayout(tile)
        column.setContentsMargins(12, 9, 12, 10)
        column.setSpacing(2)
        title = QLabel(name)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        column.addWidget(title)
        if description:
            column.addWidget(controls.small(description, self._palette))
        if tooltip:
            tile.setToolTip(fields.rich_tooltip(tooltip))
        return tile

    @staticmethod
    def _tools(entry: dict[str, Any]) -> str:
        return TOOLS_LINE.format(", ".join(entry["tools"])) if entry["tools"] else ""

    def _open_folder(self) -> None:
        path = describe_local_skills()["path"]
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _create_example(self) -> None:
        write_example_skill()
        self.refresh()


def _grid(tiles: list[QWidget]) -> QWidget:
    holder = QWidget()
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(GRID_GAP)
    for index, tile in enumerate(tiles):
        grid.addWidget(tile, index // GRID_COLUMNS, index % GRID_COLUMNS)
    for column in range(GRID_COLUMNS):
        grid.setColumnStretch(column, 1)
    return holder
