from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr, tr_n
from ai_agent.ui import style

STEP_FONT_SCALE = 0.92
BUTTON_HEIGHT = 26
PENDING_MARK = "◆"
APPLIED_MARK = "✓"
CANCELLED_MARK = "—"
FAILED_MARK = "✕"
NUMBER_WIDTH = 16


class PlanCard(QFrame):
    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, steps: list[str], parent=None):
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
        label.setWordWrap(True)
        label.setStyleSheet("border: none;")
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        label.setFont(font)
        number.setFont(font)
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


def _accent_button(palette) -> str:
    accent = style.css_color(style.accent(palette))
    return (
        f"QPushButton {{ background: {accent};"
        f"color: {style.css_color(palette.highlightedText().color())};"
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
    return tr_n("Will change the project — %n step(s)", count)
