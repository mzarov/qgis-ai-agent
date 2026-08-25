from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui import style

PENDING = "•"
DONE = "✓"
FAILED = "✕"
REJECTED = "⊘"
STEP_FONT_SCALE = 0.9
STEPS_INDENT = 22


class ActivityGroup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet(
            f"QFrame {{ border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {style.CARD_RADIUS}px; }}"
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header(palette))
        column.addWidget(self._build_steps(palette))
        self._steps_count = 0
        self._failed = False
        self._collapse()

    def _build_header(self, palette) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(9, 6, 10, 6)
        row.setSpacing(7)

        self._toggle = QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setStyleSheet("QToolButton { border: none; }")
        self._toggle.toggled.connect(self._on_toggled)
        row.addWidget(self._toggle)

        self._title = QLabel()
        self._title.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        row.addWidget(self._title, 1)

        self._status = QLabel()
        self._status.setStyleSheet("border: none;")
        row.addWidget(self._status)
        return header

    def _build_steps(self, palette) -> QWidget:
        self._steps_holder = QWidget()
        self._steps = QVBoxLayout(self._steps_holder)
        self._steps.setContentsMargins(STEPS_INDENT, 0, 10, 8)
        self._steps.setSpacing(3)
        self._steps_holder.setStyleSheet(
            f"color: {style.css_color(style.muted(palette))}; border: none;"
        )
        return self._steps_holder

    def add_step(self, text: str) -> QLabel:
        label = QLabel(f"{PENDING}  {text}")
        label.setWordWrap(True)
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        label.setFont(font)
        self._steps.addWidget(label)
        self._steps_count += 1
        self._refresh_title()
        return label

    def mark_step(self, label: QLabel, ok: bool) -> None:
        marker = DONE if ok else FAILED
        label.setText(label.text().replace(PENDING, marker, 1))
        if not ok:
            self._failed = True
            self._refresh_title()

    def mark_rejected(self, label: QLabel) -> None:
        label.setText(label.text().replace(PENDING, REJECTED, 1))
        self._failed = True
        self._refresh_title()

    def _refresh_title(self) -> None:
        self._title.setText(f"{self._steps_count} {_plural(self._steps_count)}")
        self._status.setText(FAILED if self._failed else DONE)
        palette = self.palette()
        colour = palette.text().color() if self._failed else style.muted(palette)
        self._status.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")

    def _on_toggled(self, expanded: bool) -> None:
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._steps_holder.setVisible(expanded)

    def _collapse(self) -> None:
        self._toggle.setChecked(False)
        self._steps_holder.setVisible(False)


def _plural(count: int) -> str:
    tail = count % 10
    if count % 100 in range(11, 15) or tail == 0 or tail > 4:
        return "действий"
    return "действие" if tail == 1 else "действия"
