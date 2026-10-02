"""The Skills page, laid out like the Claude Code skills list.

Your skills first — active ones, then drafts still holding the example text,
then problems — and the built-in skills under them. Every skill is one row:
an icon, the name, and a muted line with its origin and description.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.local_skills import describe_local_skills, skill_choices, write_example_skill
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
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
LOCAL_ORIGIN = tr("yours")
BUILT_IN_ORIGIN = tr("built in")
DRAFT = tr("draft")
DRAFT_NOTE = tr("Write when to use it in the description line of SKILL.md to turn it on.")
EDIT = tr("Edit")
ROW_SEPARATOR = " · "
BUTTON_GAP = 8
ICON_TILE = 34
ICON_SIZE = 17
ICON_RADIUS = 8
ROW_PADDING = (0, 10, 0, 10)


class SkillsSettings:
    def __init__(self, palette: Any):
        self._palette = palette
        holder, self._column = fields.page()
        self._column.addWidget(self._header(TITLE, self._actions(palette)))
        self._column.addWidget(fields.hint(INTRO, palette))
        self._path = controls.ElidedLabel("", mode=Qt.TextElideMode.ElideMiddle)
        self._path.setStyleSheet(f"color: {style.css_color(style.faint(palette))};")
        self._path.setFont(fields.hint("", palette).font())
        self._column.addWidget(self._path)
        self._column.addSpacing(fields.SECTION_TO_CARD)
        self._list: QWidget = QWidget()
        self._list_index = self._column.count()
        self._column.addWidget(self._list)
        built_in = [choice for choice in skill_choices() if choice[2] != "local"]
        self._column.addSpacing(fields.SECTION_GAP)
        self._column.addWidget(self._header(BUILT_IN, None, len(built_in)))
        self._column.addWidget(
            fields.card_rows(
                palette,
                [self._row(name, BUILT_IN_ORIGIN, description, description) for name, description, _ in built_in],
            )
        )
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
        column.setSpacing(4)
        rows = [
            self._row(entry["name"], LOCAL_ORIGIN, entry["description"], self._tools(entry))
            for entry in described["skills"]
        ]
        rows += [self._draft(draft) for draft in described["drafts"]]
        if rows:
            column.addWidget(fields.card_rows(self._palette, rows))
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

    def _header(self, title: str, actions: QWidget | None, count: int | None = None) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, fields.SECTION_TO_CARD)
        line.setSpacing(8)
        label = QLabel(title)
        font = label.font()
        font.setBold(True)
        font.setPointSizeF(max(1.0, font.pointSizeF() * fields.SECTION_TITLE_SCALE))
        label.setFont(font)
        line.addWidget(label)
        if count is not None:
            line.addWidget(controls.badge(str(count), "neutral", self._palette), 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch(1)
        if actions is not None:
            line.addWidget(actions)
        return holder

    def _actions(self, palette: Any) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(BUTTON_GAP)
        open_button = QPushButton(OPEN_FOLDER)
        open_button.setStyleSheet(fields.ghost_button(palette))
        open_button.clicked.connect(self._open_folder)
        line.addWidget(open_button)
        example_button = QPushButton(f"+  {CREATE_EXAMPLE}")
        example_button.setStyleSheet(fields.plain_button(palette))
        example_button.clicked.connect(self._create_example)
        line.addWidget(example_button)
        return holder

    def _row(self, name: str, origin: str, description: str, tooltip: str, badge: Any = None) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(*ROW_PADDING)
        line.setSpacing(12)
        line.addWidget(self._icon())
        text = QVBoxLayout()
        text.setSpacing(2)
        title_line = QHBoxLayout()
        title_line.setSpacing(8)
        title = QLabel(name)
        title.setStyleSheet(f"color: {style.css_color(style.text(self._palette))};")
        title_line.addWidget(title)
        if badge is not None:
            title_line.addWidget(badge)
        title_line.addStretch(1)
        text.addLayout(title_line)
        detail = controls.ElidedLabel(ROW_SEPARATOR.join(part for part in (origin, description) if part))
        detail.setStyleSheet(f"color: {style.css_color(style.muted(self._palette))};")
        text.addWidget(detail)
        line.addLayout(text, 1)
        if tooltip:
            holder.setToolTip(fields.rich_tooltip(tooltip))
        holder.trailing = line
        return holder

    def _draft(self, draft: dict[str, str]) -> QWidget:
        row = self._row(draft["name"], DRAFT_NOTE, "", "", controls.badge(DRAFT, "warn", self._palette))
        edit = QPushButton(EDIT)
        edit.setStyleSheet(fields.plain_button(self._palette))
        edit.clicked.connect(lambda _checked=False, path=draft["path"]: _open(path))
        row.trailing.addWidget(edit, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _icon(self) -> QLabel:
        tile = QLabel()
        tile.setFixedSize(ICON_TILE, ICON_TILE)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setStyleSheet(
            f"QLabel {{ background: {style.css_color(style.card(self._palette))}; border-radius: {ICON_RADIUS}px; }}"
        )
        try:
            tile.setPixmap(icons.skills(style.muted(self._palette), ICON_SIZE).pixmap(ICON_SIZE, ICON_SIZE))
        except Exception:
            tile.setText("/")
        return tile

    @staticmethod
    def _tools(entry: dict[str, Any]) -> str:
        return TOOLS_LINE.format(", ".join(entry["tools"])) if entry["tools"] else ""

    def _open_folder(self) -> None:
        path = describe_local_skills()["path"]
        if path:
            _open(path)

    def _create_example(self) -> None:
        # Open the new file straight away: the example only switches on once its description is written.
        path = write_example_skill()
        self.refresh()
        if path:
            _open(path)


def _open(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
