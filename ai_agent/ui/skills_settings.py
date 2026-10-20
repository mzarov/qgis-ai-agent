from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QFontDatabase
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ai_agent.core.local_skills import builtin_skills, describe_local_skills, write_example_skill
from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields
from ai_agent.ui.skill_summaries import summary

TITLE = tr("Skills")
LEAD = tr("Instructions the agent loads for a task by itself. Type / in the chat to call a skill yourself.")
YOURS = tr("Your skills · {0}")
BUILT_IN = tr("Built in · {0}")
OPEN_FOLDER = tr("Open folder")
CREATE = tr("Create a skill")
NONE_YET = tr("No skills of your own yet.")
FOLDER_UNAVAILABLE = tr("The skills folder is unavailable in this QGIS profile.")
FIND = tr("Find a skill")
SHOW_MORE = tr("Show {0} more")
NOTHING = tr("No skill matches.")
DRAFT = tr("draft")
DRAFT_NOTE = tr("Add a description in SKILL.md to turn it on.")
EDIT = tr("Edit")
TOOLS_LINE = tr("Tools: {0}")
SLASH = "/"
SHOWN_AT_FIRST = 8
CARD_RADIUS = 8
ROW_MARGINS = (12, 10, 12, 10)
BUILT_IN_MARGINS = (12, 8, 12, 8)
NAME_WIDTH = 120
ICON_TILE = 30
ICON_SIZE = 16
ICON_RADIUS = 6
FIND_WIDTH = 180
FIND_HEIGHT = 28
HEADER_GAP = 8
PATH_GAP = 6
NOTE_SCALE = 12.5 / 13


class SkillsSettings(QObject):
    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        self._palette = palette
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        holder, self._column = fields.page(TITLE, LEAD, palette)
        self._column.addSpacing(fields.SECTION_GAP)
        self._yours_title = fields.heading("", palette)
        self._column.addLayout(self._header(self._yours_title, self._own_actions(palette)))
        self._column.addSpacing(HEADER_GAP)
        self._list: QWidget = QWidget()
        self._list_index = self._column.count()
        self._column.addWidget(self._list)
        self._column.addSpacing(PATH_GAP)
        self._path = controls.ElidedLabel("", mode=Qt.TextElideMode.ElideMiddle)
        self._path.setFont(self._mono)
        style.scale_font(self._path, fields.HINT_SCALE)
        style.ink(self._path, style.faint(palette))
        self._column.addWidget(self._path)
        self._column.addSpacing(fields.SECTION_GAP)
        built_in = builtin_skills()
        self.switches: dict[str, Any] = {}
        self._built_in_rows: list[tuple[QWidget, str]] = []
        self.find = QLineEdit()
        self.find.setPlaceholderText(FIND)
        self.find.setClearButtonEnabled(True)
        self.find.setFixedSize(FIND_WIDTH, FIND_HEIGHT)
        self.find.setStyleSheet(fields.input_style(palette))
        self.find.textChanged.connect(self._filter)
        self._column.addLayout(self._header(fields.heading(BUILT_IN.format(len(built_in)), palette), self.find))
        self._column.addSpacing(HEADER_GAP)
        self._column.addWidget(self._built_in_card(built_in))
        self._column.addStretch(1)
        self.widget: QWidget = holder
        self.refresh()

    def disabled(self) -> list[str]:
        return [name for name, switch in self.switches.items() if not switch.isChecked()]

    def refresh(self) -> None:
        described = describe_local_skills()
        self._path.setText(described["path"] or FOLDER_UNAVAILABLE)
        self._path.setToolTip(described["path"] or "")
        self._yours_title.setText(YOURS.format(len(described["skills"]) + len(described["drafts"])))
        rows = [self._own_row(entry) for entry in described["skills"]]
        rows += [self._draft_row(draft) for draft in described["drafts"]]
        fresh = QWidget()
        column = QVBoxLayout(fresh)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        if not rows:
            empty = fields.hint(NONE_YET, self._palette)
            empty.setContentsMargins(*ROW_MARGINS)
            rows = [empty]
        column.addWidget(self._card(rows))
        for problem in described["problems"]:
            warning = fields.hint(problem, self._palette)
            style.ink(warning, style.danger(self._palette))
            column.addWidget(warning)
        self._column.insertWidget(self._list_index, fresh)
        self._list.hide()
        self._list.deleteLater()
        self._list = fresh

    def _header(self, title: QLabel, actions: Any) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setSpacing(HEADER_GAP)
        line.addWidget(title, 1)
        if isinstance(actions, QWidget):
            line.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            line.addLayout(actions)
        return line

    def _own_actions(self, palette: Any) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setSpacing(HEADER_GAP)
        folder = QPushButton(OPEN_FOLDER)
        folder.setStyleSheet(fields.plain_button(palette))
        folder.clicked.connect(self._open_folder)
        line.addWidget(folder)
        create = QPushButton(f"+  {CREATE}")
        create.setStyleSheet(fields.plain_button(palette))
        create.clicked.connect(self._create)
        line.addWidget(create)
        return line

    def _card(self, rows: list[QWidget]) -> QWidget:
        card = controls.RoundedFrame(CARD_RADIUS)
        card.set_look(style.surface(self._palette).name(), style.hairline(self._palette).name())
        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        fields.add_rows(column, self._palette, rows)
        return card

    def _own_row(self, entry: dict[str, Any]) -> QWidget:
        row = self._skill_row(entry["name"], entry["description"])
        if entry["tools"]:
            row.setToolTip(controls.plain_tip(TOOLS_LINE.format(", ".join(entry["tools"]))))
        row.trailing.addWidget(self._edit_button(entry.get("path", "")), 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _draft_row(self, draft: dict[str, str]) -> QWidget:
        row = self._skill_row(draft["name"], DRAFT_NOTE, controls.badge(DRAFT, "warn", self._palette))
        row.trailing.addWidget(self._edit_button(draft["path"]), 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _skill_row(self, name: str, description: str, badge: Any = None) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(*ROW_MARGINS)
        line.setSpacing(12)
        line.addWidget(controls.icon_tile("skills", self._palette, ICON_TILE, ICON_SIZE, ICON_RADIUS, SLASH))
        text = QVBoxLayout()
        text.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(SLASH + name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setFont(self._mono)
        style.ink(title, style.text(self._palette))
        head.addWidget(title)
        if badge is not None:
            head.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        text.addLayout(head)
        note = controls.ElidedLabel(description)
        style.scale_font(note, NOTE_SCALE)
        style.ink(note, style.muted(self._palette))
        text.addWidget(note)
        line.addLayout(text, 1)
        holder.trailing = line
        return holder

    def _edit_button(self, path: str) -> QPushButton:
        button = QPushButton(EDIT)
        button.setStyleSheet(fields.plain_button(self._palette))
        button.setEnabled(bool(path))
        button.clicked.connect(lambda _checked=False, target=path: _open(target))
        return button

    def _built_in_card(self, skills: list[tuple[str, str, bool]]) -> QWidget:
        card = controls.RoundedFrame(CARD_RADIUS)
        card.set_look(style.surface(self._palette).name(), style.hairline(self._palette).name())
        column = QVBoxLayout(card)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for name, description, enabled in skills:
            row, line = self._lined_row()
            title = QLabel(SLASH + name)
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setFont(self._mono)
            title.setFixedWidth(NAME_WIDTH)
            style.ink(title, style.text(self._palette))
            line.addWidget(title)
            text = summary(name, description)
            note = controls.ElidedLabel(text)
            style.scale_font(note, NOTE_SCALE)
            style.ink(note, style.muted(self._palette))
            line.addWidget(note, 1)
            switch = fields.switch(self._palette)
            switch.setChecked(enabled)
            switch.toggled.connect(lambda _on: self.changed.emit())
            line.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
            self.switches[name] = switch
            column.addWidget(row)
            self._built_in_rows.append((row, f"{name} {text} {description}".casefold()))
        self._more_row, more_line = self._lined_row()
        self._more = QPushButton()
        self._more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more.setStyleSheet(_link_style(self._palette))
        self._more.clicked.connect(self._show_all)
        more_line.addWidget(self._more, 1)
        column.addWidget(self._more_row)
        self._nothing = fields.hint(NOTHING, self._palette)
        self._nothing.setContentsMargins(*BUILT_IN_MARGINS)
        column.addWidget(self._nothing)
        self._showing_all = False
        self._filter("")
        return card

    def _lined_row(self) -> tuple[QWidget, QHBoxLayout]:
        row = QWidget()
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        row.top_line = fields.separator(self._palette)
        outer.addWidget(row.top_line)
        inner = QWidget()
        line = QHBoxLayout(inner)
        line.setContentsMargins(*BUILT_IN_MARGINS)
        line.setSpacing(12)
        outer.addWidget(inner)
        return row, line

    def _show_all(self) -> None:
        self._showing_all = True
        self._filter(self.find.text())

    def _filter(self, text: str) -> None:
        words = text.casefold().split()
        matches = [row for row, haystack in self._built_in_rows if all(word in haystack for word in words)]
        limit = len(matches) if words or self._showing_all else SHOWN_AT_FIRST
        shown = matches[:limit]
        for row, _haystack in self._built_in_rows:
            row.setVisible(row in shown)
        for index, row in enumerate(shown):
            row.top_line.setVisible(index > 0)
        hidden = len(matches) - len(shown)
        self._more.setText(SHOW_MORE.format(hidden))
        self._more_row.setVisible(hidden > 0)
        self._nothing.setVisible(not matches)

    def _open_folder(self) -> None:
        path = describe_local_skills()["path"]
        if path:
            _open(path)

    def _create(self) -> None:
        path = write_example_skill()
        self.refresh()
        if path:
            _open(path)


def usable_count() -> int:
    return sum(enabled for _name, _description, enabled in builtin_skills()) + len(describe_local_skills()["skills"])


def _open(path: str) -> None:
    if path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _link_style(palette: Any) -> str:
    return (
        "QPushButton { background: transparent; border: none; padding: 8px;"
        f"color: {style.css_color(style.accent(palette))}; }}"
        f"QPushButton:hover {{ color: {style.css_color(style.accent_hover(palette))}; }}"
    )
