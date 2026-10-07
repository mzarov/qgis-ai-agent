"""The Memory section of Personalisation: short notes about the user the agent keeps across projects.

The list is edited here and stored on Save, like every other setting; the
agent adds notes itself through `remember` with about=user while the switch
below allows it.
"""

from typing import Any

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget

from ai_agent.core.personal import MAX_NOTE_CHARS, MAX_NOTES, user_notes
from ai_agent.i18n import tr
from ai_agent.ui import settings_fields as fields
from ai_agent.ui import style

NO_NOTES = tr("No notes yet.")
ADD = tr("Add")
NOTE_PLACEHOLDER = tr("For example: I work in EPSG:32637 and export to GeoPackage")
REMOVE = tr("Remove this note")
REMOVE_MARK = "×"
ROW_PADDING = (0, 6, 0, 6)
LIST_GAP = 8


class MemoryNotes(QObject):
    """The notes as rows with a remove button, and a field to add one."""

    changed = pyqtSignal()

    def __init__(self, palette: Any):
        super().__init__()
        self._palette = palette
        self.notes = user_notes()
        self.widget = QWidget()
        column = QVBoxLayout(self.widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(LIST_GAP)
        self._list = QVBoxLayout()
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(0)
        column.addLayout(self._list)
        line = QHBoxLayout()
        line.setSpacing(LIST_GAP)
        self.editor = QLineEdit()
        self.editor.setPlaceholderText(NOTE_PLACEHOLDER)
        self.editor.setMaxLength(MAX_NOTE_CHARS)
        self.editor.setStyleSheet(fields.input_style(palette))
        self.editor.returnPressed.connect(self.add)
        line.addWidget(self.editor, 1)
        self.add_button = QPushButton(ADD)
        self.add_button.setStyleSheet(fields.plain_button(palette))
        self.add_button.clicked.connect(self.add)
        line.addWidget(self.add_button)
        column.addLayout(line)
        self._rows: list[QWidget] = []
        self._render()

    def add(self) -> None:
        note = self.editor.text().strip()
        if not note or note in self.notes or len(self.notes) >= MAX_NOTES:
            return
        self.notes.append(note)
        self.editor.clear()
        self._render()
        self.changed.emit()

    def remove(self, note: str) -> None:
        if note in self.notes:
            self.notes.remove(note)
            self._render()
            self.changed.emit()

    def _render(self) -> None:
        for row in self._rows:
            self._list.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._rows = [self._row(note) for note in self.notes] or [fields.hint(NO_NOTES, self._palette)]
        for row in self._rows:
            self._list.addWidget(row)

    def _row(self, note: str) -> QWidget:
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(*ROW_PADDING)
        line.setSpacing(LIST_GAP)
        text = QLabel(note)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(True)
        style.ink(text, style.text(self._palette))
        line.addWidget(text, 1)
        remove = QToolButton()
        remove.setText(REMOVE_MARK)
        remove.setToolTip(REMOVE)
        remove.setAutoRaise(True)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda _checked=False, chosen=note: self.remove(chosen))
        line.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        return holder
