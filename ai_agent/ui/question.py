"""The agent's question as a card, as in Claude Code: up to three answers and a fourth row to type one's own.

A click on an answer, or Enter in the fourth row, sends that text as the reply;
the main composer still works too. Once answered — however — the card folds to
its question, so an old card never offers a stale choice. Number keys pick an
answer while the card has focus. Rows paint their hover, nothing restyles in an event.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

ROW_RADIUS = 8
NUMBER_WIDTH = 18
OWN_ANSWER = tr("Type another answer and press Enter")
NUMBER_KEYS = {getattr(Qt.Key, f"Key_{digit}"): digit - 1 for digit in range(1, 10)}


class AnswerRow(controls.RoundedFrame):
    clicked = pyqtSignal(str)

    def __init__(self, number: int, text: str, palette: Any, parent: QWidget | None = None):
        super().__init__(ROW_RADIUS, parent)
        self.text = text
        self._fill = style.card(palette).name()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 7, 10, 7)
        line.setSpacing(8)
        line.addWidget(_number(number, palette), 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(label, 1)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.text)

    def enterEvent(self, event: Any) -> None:
        self.set_look(self._fill, None)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.set_look(None, None)
        super().leaveEvent(event)


class QuestionCard(controls.RoundedFrame):
    answered = pyqtSignal(str)

    def __init__(self, question: str, options: list[str], palette: Any, parent: QWidget | None = None):
        super().__init__(style.CARD_RADIUS, parent)
        self.set_look(None, style.hairline(palette).name())
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        column = QVBoxLayout(self)
        column.setContentsMargins(6, 10, 6, 8)
        column.setSpacing(2)
        self.question = QLabel(question)
        self.question.setWordWrap(True)
        self.question.setContentsMargins(10, 0, 10, 4)
        self.question.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        style.scale_font(self.question, 1.0, bold=True)
        self.question.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        column.addWidget(self.question)
        self.rows: list[AnswerRow] = []
        for number, option in enumerate(options, 1):
            row = AnswerRow(number, option, palette)
            row.clicked.connect(self._send)
            column.addWidget(row)
            self.rows.append(row)
        self._own = QWidget()
        own = QHBoxLayout(self._own)
        own.setContentsMargins(10, 4, 10, 0)
        own.setSpacing(8)
        own.addWidget(_number(len(options) + 1, palette), 0, Qt.AlignmentFlag.AlignVCenter)
        self.editor = QLineEdit()
        self.editor.setPlaceholderText(OWN_ANSWER)
        self.editor.setStyleSheet(fields.input_style(palette))
        self.editor.returnPressed.connect(lambda: self._send(self.editor.text()))
        own.addWidget(self.editor, 1)
        column.addWidget(self._own)

    def _send(self, text: str) -> None:
        reply = text.strip()
        if not reply:
            return
        self.retire()
        self.answered.emit(reply)

    def retire(self) -> None:
        """Fold to the question: the reply now sits in the chat as the user's message."""
        for row in self.rows:
            row.setVisible(False)
        self._own.setVisible(False)

    @property
    def is_open(self) -> bool:
        return not self._own.isHidden()

    def keyPressEvent(self, event: Any) -> None:
        index = NUMBER_KEYS.get(event.key())
        if index is not None and index < len(self.rows) and self.is_open:
            self._send(self.rows[index].text)
        elif index == len(self.rows) and self.is_open:
            self.editor.setFocus()
        else:
            super().keyPressEvent(event)


def _number(number: int, palette: Any) -> QLabel:
    label = QLabel(f"{number}.")
    label.setFixedWidth(NUMBER_WIDTH)
    label.setStyleSheet(f"color: {style.css_color(style.faint(palette))};")
    return label
