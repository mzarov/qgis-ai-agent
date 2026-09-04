from typing import Any

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.local_skills import describe_local_skills, write_example_skill
from ai_agent.i18n import tr
from ai_agent.ui import settings_fields as fields
from ai_agent.ui import style

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
BUTTON_GAP = 8


class SkillsSettings:
    def __init__(self, palette: Any):
        self._palette = palette
        holder, self._column = fields.page()
        self._column.addWidget(fields.group(TITLE, palette))
        self._column.addWidget(fields.hint(INTRO, palette))
        self._column.addSpacing(fields.GROUP_GAP)
        self._path = fields.hint("", palette)
        self._column.addWidget(self._path)
        self._column.addLayout(self._buttons(palette))
        self._column.addSpacing(fields.GROUP_GAP)
        self._list: QWidget = QWidget()
        self._list_index = self._column.count()
        self._column.addWidget(self._list)
        self._column.addStretch(1)
        self.widget: QWidget = holder
        self.refresh()

    def refresh(self) -> None:
        described = describe_local_skills()
        self._path.setText(described["path"] or FOLDER_UNAVAILABLE)
        fresh = QWidget()
        column = QVBoxLayout(fresh)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(fields.PAGE_SPACING)
        rows = [self._skill_row(entry) for entry in described["skills"]]
        if rows:
            fields.add_rows(column, self._palette, rows)
        else:
            column.addWidget(fields.hint(NONE_YET, self._palette))
        for problem in described["problems"]:
            warning = fields.hint(problem, self._palette)
            warning.setStyleSheet(f"color: {style.css_color(style.danger(self._palette))};")
            column.addWidget(warning)
        self._column.insertWidget(self._list_index, fresh)
        self._list.deleteLater()
        self._list = fresh

    def _buttons(self, palette: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(BUTTON_GAP)
        open_button = QPushButton(OPEN_FOLDER)
        open_button.setStyleSheet(fields.plain_button(palette))
        open_button.clicked.connect(self._open_folder)
        row.addWidget(open_button)
        example_button = QPushButton(CREATE_EXAMPLE)
        example_button.setStyleSheet(fields.plain_button(palette))
        example_button.clicked.connect(self._create_example)
        row.addWidget(example_button)
        row.addStretch(1)
        return row

    def _skill_row(self, entry: dict[str, Any]) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, fields.ROW_VPAD, 0, fields.ROW_VPAD)
        column.setSpacing(fields.FIELD_SPACING)
        title = QLabel(f"/{entry['name']}")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        column.addWidget(title)
        column.addWidget(fields.hint(entry["description"], self._palette))
        if entry["tools"]:
            column.addWidget(fields.hint(TOOLS_LINE.format(", ".join(entry["tools"])), self._palette))
        return holder

    def _open_folder(self) -> None:
        path = describe_local_skills()["path"]
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _create_example(self) -> None:
        write_example_skill()
        self.refresh()
