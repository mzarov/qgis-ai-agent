"""The agent's question as a card: up to three answers and a fourth row to type one's own.

Laid out like the design: "Needs clarification", the question, then option
rows with a radio, the answer, a "recommended" tag on the first (the agent lists
its pick first), a short why under it when the option carries one after " — ",
and the key that picks it. A click, a number key or Enter in the fourth row
sends the answer; the main composer still works too. Once answered the card
folds to its question, so an old card never offers a stale choice. With
"answer a question for me" set in Personalisation, a countdown takes the
recommended answer unless the user starts typing their own. Rows paint their
hover and selection; nothing restyles in an event.
"""

from typing import Any

from qgis.PyQt.QtCore import QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QFont, QPainter, QPen
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import controls, style

CARD_RADIUS = 8
ROW_RADIUS = 6
CARD_PADDING = 12
CARD_GAP = 10
ROW_GAP = 6
ROW_PADDING = (10, 8, 10, 8)
RADIO = 14
KEY = 18
TAG_RADIUS = 4
SMALL = 0.92
DETAIL = 12.5 / 13
QUESTION_SCALE = 14 / 13
# An option may explain itself after an em dash: "Natural breaks — for uneven data".
WHY = " — "
HEADING = tr("Needs clarification")
RECOMMENDED = tr("recommended")
OWN_ANSWER = tr("Your own answer…")
COUNTDOWN = tr("Choosing “{0}” in {1}")
TICK_MS = 1000
NUMBER_KEYS = {getattr(Qt.Key, f"Key_{digit}"): digit - 1 for digit in range(1, 10)}


def split_option(option: str) -> tuple[str, str]:
    """The answer and its optional explanation; only the answer goes back to the agent."""
    answer, _, why = str(option).partition(WHY)
    return answer.strip(), why.strip()


class Radio(QWidget):
    """A painted radio: a ring, and a dot when chosen."""

    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.chosen = False
        self.setFixedSize(RADIO, RADIO)

    def set_chosen(self, chosen: bool) -> None:
        self.chosen = chosen
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = style.accent(self._palette) if self.chosen else style.border_strong(self._palette)
        painter.setPen(QPen(ring, 1.25))
        painter.setBrush(QBrush(style.surface(self._palette)))
        painter.drawEllipse(QPointF(RADIO / 2, RADIO / 2), RADIO / 2 - 1, RADIO / 2 - 1)
        if self.chosen:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(style.accent(self._palette)))
            painter.drawEllipse(QPointF(RADIO / 2, RADIO / 2), 3.0, 3.0)
        painter.end()


class AnswerRow(controls.RoundedFrame):
    clicked = pyqtSignal(str)

    def __init__(self, number: int, option: str, palette: Any, recommended: bool = False, parent=None):
        super().__init__(ROW_RADIUS, parent)
        self.text, why = split_option(option)
        self._palette = palette
        self.chosen = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(*ROW_PADDING)
        line.setSpacing(8)
        self.radio = Radio(palette)
        line.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel(self.text)
        title.setWordWrap(True)
        font = title.font()
        font.setWeight(QFont.Weight.Medium)
        title.setFont(font)
        style.ink(title, style.text(palette))
        # The answer takes the width: beside a stretch a wrapping label shrinks to its hint and breaks early.
        head.addWidget(title, 1)
        if recommended:
            head.addWidget(_tag(RECOMMENDED, palette), 0, Qt.AlignmentFlag.AlignTop)
        text.addLayout(head)
        if why:
            detail = QLabel(why)
            detail.setWordWrap(True)
            style.scale_font(detail, DETAIL)
            style.ink(detail, style.muted(palette))
            text.addWidget(detail)
        line.addLayout(text, 1)
        line.addWidget(_key(str(number), palette), 0, Qt.AlignmentFlag.AlignTop)
        self._paint()

    def choose(self) -> None:
        self.chosen = True
        self.radio.set_chosen(True)
        self._paint()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.text)

    def enterEvent(self, event: Any) -> None:
        self._paint(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self._paint()
        super().leaveEvent(event)

    def _paint(self, hovered: bool = False) -> None:
        palette = self._palette
        if self.chosen:
            self.set_look(style.soft(palette, style.accent(palette)).name(), style.accent(palette).name())
        else:
            edge = style.border_strong(palette) if hovered else style.hairline(palette)
            self.set_look(style.surface(palette).name(), edge.name())


class QuestionCard(controls.RoundedFrame):
    answered = pyqtSignal(str)

    def __init__(
        self, question: str, options: list[str], palette: Any, auto_seconds: int = 0, parent: QWidget | None = None
    ):
        super().__init__(CARD_RADIUS, parent)
        self._palette = palette
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        column = QVBoxLayout(self)
        column.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        column.setSpacing(CARD_GAP)
        heading = QLabel(HEADING)
        style.scale_font(heading, SMALL)
        style.ink(heading, style.faint(palette))
        column.addWidget(heading)
        self.question = QLabel(question)
        self.question.setWordWrap(True)
        self.question.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        style.scale_font(self.question, QUESTION_SCALE, bold=True)
        style.ink(self.question, style.text(palette))
        column.addWidget(self.question)
        self._choices = QWidget()
        rows = QVBoxLayout(self._choices)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(ROW_GAP)
        self.rows: list[AnswerRow] = []
        for number, option in enumerate(options, 1):
            row = AnswerRow(number, option, palette, recommended=number == 1)
            row.clicked.connect(self._pick)
            rows.addWidget(row)
            self.rows.append(row)
        self._own = controls.RoundedFrame(ROW_RADIUS)
        self._own.set_look(style.surface(palette).name(), style.hairline(palette).name())
        own = QHBoxLayout(self._own)
        own.setContentsMargins(*ROW_PADDING)
        own.setSpacing(8)
        own.addWidget(Radio(palette), 0, Qt.AlignmentFlag.AlignVCenter)
        self.editor = QLineEdit()
        self.editor.setPlaceholderText(OWN_ANSWER)
        self.editor.setFrame(False)
        self.editor.setStyleSheet(
            f"QLineEdit {{ border: none; background: transparent; color: {style.css_color(style.text(palette))}; }}"
        )
        style.field_inks(self.editor, palette)
        self.editor.returnPressed.connect(lambda: self._send(self.editor.text()))
        own.addWidget(self.editor, 1)
        own.addWidget(_key(str(len(options) + 1), palette), 0, Qt.AlignmentFlag.AlignVCenter)
        rows.addWidget(self._own)
        column.addWidget(self._choices)
        self.countdown = controls.small("", palette)
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
            self._pick(self.rows[0].text)
        else:
            self._show_left()

    def _show_left(self) -> None:
        self.countdown.setText(COUNTDOWN.format(self.rows[0].text, f"{self._left // 60}:{self._left % 60:02d}"))
        self.countdown.setVisible(True)

    def _pick(self, text: str) -> None:
        for row in self.rows:
            if row.text == text:
                row.choose()
        self._send(text)

    def _send(self, text: str) -> None:
        reply = text.strip()
        if not reply:
            return
        self.retire()
        self.answered.emit(reply)

    def retire(self) -> None:
        """Fold to the question: the answer now sits in the trace or the chat."""
        self.stop_countdown()
        self._choices.setVisible(False)

    @property
    def is_open(self) -> bool:
        return not self._choices.isHidden()

    def keyPressEvent(self, event: Any) -> None:
        index = NUMBER_KEYS.get(event.key())
        if index is not None and index < len(self.rows) and self.is_open:
            self._pick(self.rows[index].text)
        elif index == len(self.rows) and self.is_open:
            self.editor.setFocus()
        else:
            super().keyPressEvent(event)


def _tag(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    style.scale_font(label, 11 / 13)
    accent = style.css_color(style.accent(palette))
    label.setStyleSheet(
        f"QLabel {{ color: {accent}; border: {style.HAIRLINE}px solid {accent};"
        f" border-radius: {TAG_RADIUS}px; padding: 0 5px; }}"
    )
    return label


def _key(text: str, palette: Any) -> QLabel:
    label = QLabel(text)
    label.setFixedSize(KEY, KEY)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    style.scale_font(label, 11 / 13)
    label.setStyleSheet(
        f"QLabel {{ color: {style.css_color(style.faint(palette))};"
        f" border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        f" border-radius: {TAG_RADIUS}px; }}"
    )
    return label
