"""The agent's question as a card, as in Claude Code: up to three answers and a fourth row to type one's own.

A click on an answer, or Enter in the fourth row, sends that text as the reply;
the main composer still works too. Once answered — however — the card folds to
its question, so an old card never offers a stale choice. With "answer a
question for me" set in Personalisation, a countdown takes the first answer —
the one the agent recommends — unless the user starts typing their own. Number keys pick an
answer while the card has focus. Rows paint their hover, nothing restyles in an event.
"""

from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui import settings_fields as fields

ROW_RADIUS = 8
NUMBER_WIDTH = 18
OWN_ANSWER = tr("Type another answer and press Enter")
COUNTDOWN = tr("Choosing “{0}” in {1}")
TICK_MS = 1000
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

    def __init__(
        self, question: str, options: list[str], palette: Any, auto_seconds: int = 0, parent: QWidget | None = None
    ):
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
        self.countdown = controls.small("", palette)
        self.countdown.setContentsMargins(10, 4, 10, 0)
        self.countdown.setVisible(False)
        column.addWidget(self.countdown)
        self._left = auto_seconds if self.rows else 0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        if self._left:
            self.editor.textEdited.connect(lambda _text: self.stop_countdown())
            self._show_left()
            self._timer.start()

    def stop_countdown(self) -> None:
        """The user is answering: the agent's choice must not overrule them."""
        self._timer.stop()
        self.countdown.setVisible(False)

    def _tick(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._send(self.rows[0].text)
        else:
            self._show_left()

    def _show_left(self) -> None:
        self.countdown.setText(COUNTDOWN.format(self.rows[0].text, f"{self._left // 60}:{self._left % 60:02d}"))
        self.countdown.setVisible(True)

    def _send(self, text: str) -> None:
        reply = text.strip()
        if not reply:
            return
        self.retire()
        self.answered.emit(reply)

    def retire(self) -> None:
        """Fold to the question: the reply now sits in the chat as the user's message."""
        self.stop_countdown()
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
