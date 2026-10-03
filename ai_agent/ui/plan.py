from typing import Any

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
from ai_agent.ui import controls, style
from ai_agent.ui.choice_popup import Choice, ChoiceRow

STEP_FONT_SCALE = 0.92
BUTTON_HEIGHT = 26
PENDING_MARK = "◆"
APPLIED_MARK = "✓"
CANCELLED_MARK = "—"
FAILED_MARK = "✕"
RUN_PLAN_QUESTION = tr("Run this plan?")
RUN_AUTO = tr("Run automatically")
RUN_AUTO_NOTE = tr("Changes apply by themselves; deleting still asks")
RUN_ASKING = tr("Run with approval")
RUN_ASKING_NOTE = tr("Every change waits for Apply")
KEEP_PLANNING = tr("Or reply to change the plan.")
PLAN_STARTED_AUTO = tr("Running the plan automatically")
PLAN_STARTED_ASKING = tr("Running the plan with approval")
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


class OfferRow(ChoiceRow):
    """A choice under a plan: lit under the pointer, like a row of the mode menu."""

    def enterEvent(self, event: Any) -> None:
        self.set_highlighted(True)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.set_highlighted(False)
        super().leaveEvent(event)


class PlanOffer(controls.RoundedFrame):
    """Under an answer written in plan mode, as in Claude Code: run the plan by itself or with Apply.

    A hairline card with two numbered choices; to change the plan the user just replies.
    Rows wrap and shrink with the dock, so a narrow panel never scrolls sideways.
    """

    run_requested = pyqtSignal(str)

    def __init__(self, palette, parent=None):
        super().__init__(style.CARD_RADIUS, parent)
        self.set_look(None, style.hairline(palette).name())
        column = QVBoxLayout(self)
        column.setContentsMargins(6, 10, 6, 8)
        column.setSpacing(2)
        self._question = QLabel(RUN_PLAN_QUESTION)
        self._question.setWordWrap(True)
        self._question.setContentsMargins(10, 0, 10, 4)
        style.scale_font(self._question, 1.0, bold=True)
        self._question.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        column.addWidget(self._question)
        self._rows: list[OfferRow] = []
        for number, choice in enumerate(
            (Choice(WORK_MODE_AUTO, RUN_AUTO, RUN_AUTO_NOTE), Choice(WORK_MODE_ASK, RUN_ASKING, RUN_ASKING_NOTE)), 1
        ):
            row = OfferRow(choice, number, palette, wrap=True)
            row.check.setVisible(False)
            # No number keys in the feed, so no numbers: they would promise a shortcut that is not there.
            row.number.setVisible(False)
            row.clicked.connect(self._run)
            column.addWidget(row)
            self._rows.append(row)
        self._hint = controls.small(KEEP_PLANNING, palette)
        self._hint.setContentsMargins(10, 4, 10, 0)
        column.addWidget(self._hint)

    def _run(self, mode: str) -> None:
        self.retire()
        self._question.setText(PLAN_STARTED_AUTO if mode == WORK_MODE_AUTO else PLAN_STARTED_ASKING)
        self.run_requested.emit(mode)

    def retire(self) -> None:
        for row in self._rows:
            row.setVisible(False)
        self._hint.setVisible(False)


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
