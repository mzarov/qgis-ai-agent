import time

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.i18n import tr, tr_n
from qgis_ai_agent.ui import style

COLLAPSED = "›"
EXPANDED = "⌄"
PENDING = "●"
DONE = "✓"
FAILED = "✕"
REJECTED = "⊘"
STEP_FONT_SCALE = 0.9
MARKER_WIDTH = 14
STEPS_INDENT = 26


class ActivityGroup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        palette = self.palette()
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._header = self._build_header(palette)
        column.addWidget(self._header)
        column.addWidget(self._build_steps(palette))
        self._count = 0
        self._failed = False
        self._started = time.monotonic()
        self._steps_holder.setVisible(False)

    def _build_header(self, palette) -> QWidget:
        header = QWidget()
        header.setStyleSheet("border: none;")
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 1, 2, 1)
        row.setSpacing(8)

        self._toggle = QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._toggle.setText(COLLAPSED)
        self._toggle.setFixedWidth(MARKER_WIDTH)
        self._toggle.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent;"
            f"color: {style.css_color(style.muted(palette))}; font-size: 12px; padding: 0; }}"
        )
        self._toggle.setFixedHeight(MARKER_WIDTH + 2)
        self._toggle.toggled.connect(self._on_toggled)
        row.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self._title = QLabel()
        self._title.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        row.addWidget(self._title, 1, Qt.AlignmentFlag.AlignVCenter)

        self._elapsed = QLabel()
        self._elapsed.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        self._shrink(self._elapsed)
        row.addWidget(self._elapsed, 0, Qt.AlignmentFlag.AlignVCenter)

        self._status = QLabel()
        self._status.setStyleSheet("border: none;")
        self._status.setFixedWidth(MARKER_WIDTH)
        row.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_steps(self, palette) -> QWidget:
        self._steps_holder = QWidget()
        self._steps_holder.setStyleSheet("border: none;")
        self._steps = QVBoxLayout(self._steps_holder)
        self._steps.setContentsMargins(STEPS_INDENT, 2, 2, 4)
        self._steps.setSpacing(5)
        return self._steps_holder

    def add_step(self, text: str) -> QWidget:
        row = StepRow(text, self.palette())
        self._steps.addWidget(row)
        self._count += 1
        self._refresh()
        return row

    def add_widget(self, widget: QWidget) -> None:
        self._steps.addWidget(widget)
        self._refresh()

    def reveal(self) -> None:
        self._toggle.setChecked(True)

    def rest(self) -> None:
        self._toggle.setChecked(False)

    def mark_step(self, row: "StepRow", ok: bool) -> None:
        row.set_state(DONE if ok else FAILED, ok)
        if not ok:
            self._failed = True
        self._refresh()

    def mark_rejected(self, row: "StepRow") -> None:
        row.set_state(REJECTED, False)
        self._failed = True
        self._refresh()

    def _refresh(self) -> None:
        palette = self.palette()
        self._header.setVisible(bool(self._count))
        self._steps.setContentsMargins(STEPS_INDENT if self._count else 0, 2, 2, 4)
        self._title.setText(tr_n("%n action(s)", self._count))
        self._status.setText(FAILED if self._failed else DONE)
        colour = style.danger(palette) if self._failed else style.success(palette)
        self._status.setStyleSheet(f"color: {style.css_color(colour)}; border: none;")
        self._elapsed.setText(_format_seconds(time.monotonic() - self._started))

    def _on_toggled(self, expanded: bool) -> None:
        self._toggle.setText(EXPANDED if expanded else COLLAPSED)
        self._steps_holder.setVisible(expanded)

    @staticmethod
    def _shrink(label: QLabel) -> None:
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        label.setFont(font)


class StepRow(QWidget):
    def __init__(self, text: str, palette, parent=None):
        super().__init__(parent)
        self.setStyleSheet("border: none;")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._marker = QLabel(PENDING)
        self._marker.setFixedWidth(MARKER_WIDTH)
        self._marker.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        row.addWidget(self._marker)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {style.css_color(style.muted(palette))};")
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * STEP_FONT_SCALE))
        label.setFont(font)
        self._marker.setFont(font)
        row.addWidget(label, 1)

    def set_state(self, marker: str, ok: bool) -> None:
        palette = self.palette()
        colour = style.success(palette) if ok else style.danger(palette)
        self._marker.setText(marker)
        self._marker.setStyleSheet(f"color: {style.css_color(colour)};")


def _format_seconds(seconds: float) -> str:
    if seconds < 1:
        return tr("{0} ms").format(int(seconds * 1000))
    if seconds < 60:
        return tr("{0} s").format(f"{seconds:.1f}")
    return tr("{0} min {1} s").format(int(seconds // 60), int(seconds % 60))
