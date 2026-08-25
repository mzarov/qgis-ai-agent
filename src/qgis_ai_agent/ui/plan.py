from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui import style

STEP_FONT_SCALE = 0.92
BUTTON_HEIGHT = 28
APPLIED_MARK = "✓"
CANCELLED_MARK = "—"


class PlanCard(QFrame):
    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet(
            f"QFrame {{ background: {style.css_color(style.card(palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(11, 9, 11, 10)
        column.setSpacing(7)

        self._heading = QLabel(_heading(len(steps)))
        self._heading.setStyleSheet("border: none;")
        font = self._heading.font()
        font.setBold(True)
        self._heading.setFont(font)
        column.addWidget(self._heading)
        column.addWidget(self._build_steps(steps, palette))

        self._buttons = self._build_buttons()
        column.addWidget(self._buttons)

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
            f"border-top: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(8)

        number = QLabel(str(index))
        number.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        layout.addWidget(number)

        label = QLabel(step)
        label.setWordWrap(True)
        label.setStyleSheet("border: none;")
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        label.setFont(font)
        layout.addWidget(label, 1)
        return row

    def _build_buttons(self) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)

        apply_button = QPushButton("Применить")
        apply_button.setMinimumHeight(BUTTON_HEIGHT)
        apply_button.setDefault(True)
        apply_button.clicked.connect(self.confirmed.emit)
        row.addWidget(apply_button, 1)

        cancel_button = QPushButton("Отмена")
        cancel_button.setMinimumHeight(BUTTON_HEIGHT)
        cancel_button.clicked.connect(self.cancelled.emit)
        row.addWidget(cancel_button)
        return holder

    def mark_applied(self) -> None:
        self._settle(f"{APPLIED_MARK} Применено")

    def mark_cancelled(self) -> None:
        self._settle(f"{CANCELLED_MARK} Отменено")

    def _settle(self, heading: str) -> None:
        self._heading.setText(heading)
        self._heading.setStyleSheet(
            f"color: {style.css_color(style.muted(self.palette()))}; border: none;"
        )
        self._buttons.setVisible(False)


def _heading(count: int) -> str:
    tail = count % 10
    if count % 100 in range(11, 15) or tail == 0 or tail > 4:
        word = "шагов"
    elif tail == 1:
        word = "шаг"
    else:
        word = "шага"
    return f"Изменит проект — {count} {word}"
