from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.core.settings import WORK_MODE_ASK, WORK_MODE_AUTO
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import style

STEP_FONT_SCALE = 0.92
BUTTON_HEIGHT = 26
PENDING_MARK = "◆"
APPLIED_MARK = "✓"
CANCELLED_MARK = "—"
FAILED_MARK = "✕"
RUN_PLAN_QUESTION = tr("Run this plan?")
RUN_ASKING = tr("Run with approval")
RUN_AUTO = tr("Run automatically")
PLAN_STARTED = tr("Running the plan")
NUMBER_WIDTH = 16


class PlanCard(QFrame):
    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, steps: list[str], applies_itself: bool = False, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet(
            f"QFrame {{ background: transparent;"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(11, 8, 11, 9)
        column.setSpacing(6)
        column.addWidget(self._build_heading(len(steps), palette))
        column.addWidget(self._build_steps(steps, palette))
        self._buttons = self._build_buttons(palette)
        column.addWidget(self._buttons)
        if applies_itself:
            # Auto mode: nothing to press, the card only reports what is being applied.
            self._buttons.setVisible(False)
            self._heading.setText(_auto_heading(len(steps)))
            self._mark.setStyleSheet(f"color: {style.css_color(style.accent(palette))};")

    def _build_heading(self, count: int, palette) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._mark = QLabel(PENDING_MARK)
        self._mark.setFixedWidth(NUMBER_WIDTH)
        self._mark.setStyleSheet(f"color: {style.css_color(style.warning(palette))};")
        row.addWidget(self._mark)

        self._heading = QLabel(_heading(count))
        font = self._heading.font()
        font.setBold(True)
        self._heading.setFont(font)
        self._heading.setStyleSheet("border: none;")
        row.addWidget(self._heading, 1)
        return holder

    def _build_steps(self, steps: list[str], palette) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("border: none;")
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for index, step in enumerate(steps, 1):
            column.addWidget(self._build_step(index, step, palette))
        return holder

    @staticmethod
    def _build_step(index: int, step: str, palette) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            f"border: none; border-top: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(8)

        number = QLabel(f"{index}.")
        number.setFixedWidth(NUMBER_WIDTH)
        number.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        layout.addWidget(number)

        label = QLabel(step)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setStyleSheet("border: none;")
        style.scale_font(label, STEP_FONT_SCALE)
        number.setFont(label.font())
        layout.addWidget(label, 1)
        return row

    def _build_buttons(self, palette) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(NUMBER_WIDTH + 8, 2, 0, 0)
        row.setSpacing(8)

        apply_button = QPushButton(tr("Apply"))
        apply_button.setMinimumHeight(BUTTON_HEIGHT)
        apply_button.setCursor(apply_button.cursor())
        apply_button.setStyleSheet(_accent_button(palette))
        apply_button.clicked.connect(self.confirmed.emit)
        row.addWidget(apply_button, 1)

        cancel_button = QPushButton(tr("Cancel"))
        cancel_button.setMinimumHeight(BUTTON_HEIGHT)
        cancel_button.setStyleSheet(_plain_button(palette))
        cancel_button.clicked.connect(self.cancelled.emit)
        row.addWidget(cancel_button)
        return holder

    def mark_applied(self) -> None:
        self._settle(APPLIED_MARK, tr("Applied"), style.success(self.palette()))

    def mark_cancelled(self) -> None:
        self._settle(CANCELLED_MARK, tr("Cancelled"), style.muted(self.palette()))

    def mark_failed(self) -> None:
        self._settle(FAILED_MARK, tr("Applied with errors"), style.danger(self.palette()))

    def _settle(self, mark: str, heading: str, colour) -> None:
        self._mark.setText(mark)
        self._mark.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")
        self._heading.setText(heading)
        self._heading.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")
        self._buttons.setVisible(False)


class PlanOffer(QFrame):
    """Under an answer written in plan mode: run the plan, asking first or by itself, or keep planning.

    Keeping planning needs no button: the user just types the next message.
    """

    run_requested = pyqtSignal(str)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)
        self._question = QLabel(RUN_PLAN_QUESTION)
        self._question.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        row.addWidget(self._question)
        self._buttons: list[QPushButton] = []
        for text, mode, look in (
            (RUN_ASKING, WORK_MODE_ASK, _plain_button(palette)),
            (RUN_AUTO, WORK_MODE_AUTO, _accent_button(palette)),
        ):
            button = QPushButton(text)
            button.setMinimumHeight(BUTTON_HEIGHT)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(look)
            button.clicked.connect(lambda _checked=False, chosen=mode: self._run(chosen))
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch(1)

    def _run(self, mode: str) -> None:
        self.retire()
        self._question.setText(PLAN_STARTED)
        self.run_requested.emit(mode)

    def retire(self) -> None:
        for button in self._buttons:
            button.setVisible(False)


def _accent_button(palette) -> str:
    accent = style.css_color(style.accent(palette))
    return (
        f"QPushButton {{ background: {accent};"
        f"color: {style.css_color(style.on_accent(palette))};"
        f"border: {style.HAIRLINE}px solid {accent}; border-radius: 6px;"
        "padding: 0 14px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {style.css_color(style.accent(palette).lighter(112))}; }}"
    )


def _plain_button(palette) -> str:
    border = style.css_color(style.hairline(palette))
    return (
        f"QPushButton {{ background: transparent; color: {style.css_color(style.text(palette))};"
        f"border: {style.HAIRLINE}px solid {border}; border-radius: 6px; padding: 0 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
    )


def _heading(count: int) -> str:
    return tr_n("Ready to run — %n action(s)", count)


def _auto_heading(count: int) -> str:
    return tr_n("Applying by itself — %n action(s)", count)
