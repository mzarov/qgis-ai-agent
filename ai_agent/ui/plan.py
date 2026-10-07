from typing import Any

from qgis.PyQt.QtCore import Qt, QTime, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.core.orchestrator.notices import STEP_DONE, STEP_FAILED, STEP_RUNNING, STEP_SKIPPED
from ai_agent.core.settings import WORK_MODE_ASK, WORK_MODE_AUTO
from ai_agent.i18n import tr, tr_n
from ai_agent.ui import controls, style
from ai_agent.ui.choice_popup import Choice, ChoiceRow

SUB_SCALE = 0.92
BUTTON_HEIGHT = 32
CARD_RADIUS = 8
CONTROL_RADIUS = 6
HEADER_PADDING = (12, 10, 12, 10)
ROW_PADDING = (12, 9, 12, 9)
FOOTER_PADDING = (12, 10, 12, 12)
STATUS_PADDING = (12, 8, 12, 8)
NUMBER_WIDTH = 18
MARK_SIZE = 12
CANCELLED_OPACITY = 0.55
# A plan line may end in what Undo cannot take back ("· writes outside the project…"); it becomes the sub-line.
SUB_SEPARATOR = " · "
PENDING_MARK = "◆"
APPLIED_MARK = "✓"
CANCELLED_MARK = "—"
FAILED_MARK = "✕"
UNDONE_MARK = "↺"
RUNNING_MARK = "●"
RUN_PLAN_QUESTION = tr("Run this plan?")
RUN_AUTO = tr("Run automatically")
RUN_AUTO_NOTE = tr("Changes apply by themselves; deleting still asks")
RUN_ASKING = tr("Run with approval")
RUN_ASKING_NOTE = tr("Every change waits for Apply")
KEEP_PLANNING = tr("Or reply to change the plan.")
PLAN_STARTED_AUTO = tr("Running the plan automatically")
PLAN_STARTED_ASKING = tr("Running the plan with approval")
UNDO_HINT = tr("Applied changes can be undone from this card.")
APPLIED_AT = tr("Applied at {0}")
UNDONE_AT = tr("Undone at {0}")
NOTHING_CHANGED = tr("Nothing changed")
UNDO = tr("Undo")
FAILED_TITLE = tr("Applied with errors")
CANCELLED_TITLE = tr("Plan cancelled")
UNDONE_TITLE = tr("Undone")
TIME_FORMAT = "HH:mm"
# A plan step's mark while the plan applies, by the state the orchestrator reports.
STEP_MARKS = {
    STEP_RUNNING: (RUNNING_MARK, style.muted),
    STEP_DONE: (APPLIED_MARK, style.success),
    STEP_FAILED: (FAILED_MARK, style.danger),
    STEP_SKIPPED: (CANCELLED_MARK, style.muted),
}


def split_line(line: str) -> tuple[str, str]:
    """A plan line as its step and the kind of change it is, the sub-line under it."""
    step, separator, kind = str(line).rpartition(SUB_SEPARATOR)
    return (step, kind) if separator else (str(line), "")


class PlanCard(controls.RoundedFrame):
    """The plan: a header with its count, the numbered steps, then Apply and Cancel; after it, Undo.

    The only card in the feed besides a question, because only they ask for an action.
    While the plan applies each step marks its progress; afterwards the footer says when
    it was applied and offers to undo it from the snapshot the apply took.
    """

    confirmed = pyqtSignal()
    cancelled = pyqtSignal()
    undo_requested = pyqtSignal()

    def __init__(self, steps: list[str], applies_itself: bool = False, parent=None):
        super().__init__(CARD_RADIUS, parent)
        palette = self._palette = self.palette()
        self._count = len(steps)
        self.set_look(style.surface(palette).name(), style.hairline(palette).name())
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_heading(palette))
        column.addWidget(_divider(palette))
        self._list = self._build_steps(steps, palette)
        column.addWidget(self._list)
        self._footer_line = _divider(palette)
        column.addWidget(self._footer_line)
        self._buttons = self._build_buttons(palette)
        column.addWidget(self._buttons)
        self._status = self._build_status(palette)
        column.addWidget(self._status)
        self._status.setVisible(False)
        if applies_itself:
            # Auto mode: nothing to press, the card only reports what is being applied.
            self._buttons.setVisible(False)
            self._footer_line.setVisible(False)
            self._heading.setText(tr_n("Applying by itself · %n change(s)", self._count))
            self._paint_mark(PENDING_MARK, style.accent(palette))

    def _build_heading(self, palette: Any) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(*HEADER_PADDING)
        row.setSpacing(8)
        self._mark = QLabel()
        self._mark.setFixedWidth(MARK_SIZE + 2)
        row.addWidget(self._mark)
        self._heading = QLabel(tr_n("Plan · %n change(s)", self._count))
        font = self._heading.font()
        font.setBold(True)
        self._heading.setFont(font)
        style.ink(self._heading, style.text(palette))
        row.addWidget(self._heading, 1)
        self._paint_mark(PENDING_MARK, style.accent(palette))
        return holder

    def _build_steps(self, steps: list[str], palette: Any) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._steps: list[PlanStep] = []
        for index, step in enumerate(steps, 1):
            if index > 1:
                column.addWidget(_divider(palette))
            self._steps.append(PlanStep(index, step, palette))
            column.addWidget(self._steps[-1])
        return holder

    def _build_buttons(self, palette: Any) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(*FOOTER_PADDING)
        column.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        apply_button = QPushButton(tr("Apply"))
        apply_button.setFixedHeight(BUTTON_HEIGHT)
        apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_button.setStyleSheet(_accent_button(palette))
        apply_button.clicked.connect(self.confirmed.emit)
        row.addWidget(apply_button, 1)
        cancel_button = QPushButton(tr("Cancel"))
        cancel_button.setFixedHeight(BUTTON_HEIGHT)
        cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_button.setStyleSheet(_plain_button(palette))
        cancel_button.clicked.connect(self.cancelled.emit)
        row.addWidget(cancel_button)
        column.addLayout(row)
        hint = controls.small(UNDO_HINT, palette)
        style.ink(hint, style.faint(palette))
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(hint)
        return holder

    def _build_status(self, palette: Any) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(*STATUS_PADDING)
        row.setSpacing(8)
        self._status_text = controls.small("", palette)
        style.ink(self._status_text, style.faint(palette))
        row.addWidget(self._status_text, 1)
        self._undo = QPushButton(UNDO)
        self._undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo.setStyleSheet(_link_button(palette))
        self._undo.clicked.connect(self.undo_requested.emit)
        self._undo.setVisible(False)
        row.addWidget(self._undo)
        return holder

    def mark_step(self, index: int, state: str, note: str = "") -> None:
        """One step's progress while the plan applies: running, done, failed with the reason, or skipped."""
        if 0 <= index < len(self._steps):
            self._steps[index].set_state(state, note)

    def mark_applied(self, undoable: bool = False) -> None:
        self._settle(APPLIED_MARK, tr_n("Applied · %n change(s)", self._count), style.success(self._palette))
        self._show_status(APPLIED_AT.format(_now()), undoable)

    def mark_failed(self, undoable: bool = False) -> None:
        self._settle(FAILED_MARK, FAILED_TITLE, style.danger(self._palette))
        self._show_status(APPLIED_AT.format(_now()), undoable)

    def mark_cancelled(self) -> None:
        self._settle(CANCELLED_MARK, CANCELLED_TITLE, style.muted(self._palette))
        effect = QGraphicsOpacityEffect(self._list)
        effect.setOpacity(CANCELLED_OPACITY)
        self._list.setGraphicsEffect(effect)
        self._show_status(NOTHING_CHANGED, False)

    def mark_undone(self) -> None:
        self._settle(UNDONE_MARK, UNDONE_TITLE, style.muted(self._palette))
        self._show_status(UNDONE_AT.format(_now()), False)

    def _settle(self, mark: str, heading: str, colour: Any) -> None:
        self._paint_mark(mark, colour)
        self._heading.setText(heading)
        self._buttons.setVisible(False)

    def _show_status(self, text: str, undoable: bool) -> None:
        self._footer_line.setVisible(True)
        self._status_text.setText(text)
        self._undo.setVisible(undoable)
        self._status.setVisible(True)

    def _paint_mark(self, mark: str, colour: Any) -> None:
        self._mark.setText(mark)
        style.ink(self._mark, colour)


class PlanStep(QWidget):
    """A numbered step and, under it, the kind of change; while applying a mark at the end and, if it
    failed, the reason under it."""

    def __init__(self, index: int, step: str, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._palette = palette
        self.state = ""
        text, kind = split_line(step)
        grid = QGridLayout(self)
        grid.setContentsMargins(*ROW_PADDING)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        number = QLabel(f"{index}.")
        number.setFixedWidth(NUMBER_WIDTH)
        style.ink(number, style.faint(palette))
        grid.addWidget(number, 0, 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(text)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        # Explicit ink: a style sheet freezes the palette it was polished with, and that can be the
        # QGIS palette rather than the panel's when the panel theme differs from QGIS.
        self.label.setStyleSheet(f"border: none; color: {style.css_color(style.text(palette))};")
        grid.addWidget(self.label, 0, 1)
        self.mark = QLabel()
        self.mark.setVisible(False)
        grid.addWidget(self.mark, 0, 2, Qt.AlignmentFlag.AlignTop)
        self.kind = controls.small(kind, palette)
        self.kind.setTextFormat(Qt.TextFormat.PlainText)
        style.scale_font(self.kind, SUB_SCALE / controls.SMALL_SCALE)
        style.ink(self.kind, style.muted(palette))
        self.kind.setVisible(bool(kind))
        grid.addWidget(self.kind, 1, 1)
        self.reason = controls.small("", palette)
        self.reason.setTextFormat(Qt.TextFormat.PlainText)
        self.reason.setStyleSheet(f"color: {style.css_color(style.danger(palette))}; border: none;")
        self.reason.setVisible(False)
        grid.addWidget(self.reason, 2, 1)
        grid.setColumnStretch(1, 1)

    def set_state(self, state: str, note: str = "") -> None:
        self.state = state
        mark, colour = STEP_MARKS.get(state, ("", style.muted))
        self.mark.setText(mark)
        self.mark.setVisible(bool(mark))
        self.mark.setStyleSheet(f"color: {style.css_color(colour(self._palette))}; border: none;")
        failed = state == STEP_FAILED
        self.reason.setText(note if failed else "")
        self.reason.setVisible(failed and bool(note))


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


def _divider(palette: Any) -> QWidget:
    line = QWidget()
    line.setFixedHeight(style.HAIRLINE)
    style.fill(line, style.hairline(palette))
    return line


def _now() -> str:
    return QTime.currentTime().toString(TIME_FORMAT)


def _accent_button(palette: Any) -> str:
    accent = style.css_color(style.accent(palette))
    hover = style.css_color(style.accent_hover(palette))
    return (
        f"QPushButton {{ background: {accent}; color: {style.css_color(style.on_accent(palette))};"
        f" border: {style.HAIRLINE}px solid {accent}; border-radius: {CONTROL_RADIUS}px;"
        " padding: 0 14px; font-weight: 600; }"
        f"QPushButton:hover {{ background: {hover}; border-color: {hover}; }}"
    )


def _plain_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: {style.css_color(style.surface(palette))};"
        f" color: {style.css_color(style.text(palette))};"
        f" border: {style.HAIRLINE}px solid {style.css_color(style.border_strong(palette))};"
        f" border-radius: {CONTROL_RADIUS}px; padding: 0 14px; }}"
        f"QPushButton:hover {{ background: {style.css_color(style.card(palette))}; }}"
    )


def _link_button(palette: Any) -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {style.css_color(style.accent(palette))};"
        " padding: 2px 4px; border-radius: 4px; }"
        f"QPushButton:hover {{ background: {style.css_color(style.soft(palette, style.accent(palette)))}; }}"
    )
