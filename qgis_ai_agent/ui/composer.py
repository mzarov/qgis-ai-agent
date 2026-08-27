from typing import Any

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.i18n import tr
from qgis_ai_agent.ui import style

PLACEHOLDER = tr("Ask about the project or ask to process layers")
MIN_HEIGHT = 34
MAX_HEIGHT = 120
SEND_SIZE = 26
HINT_FONT_SCALE = 0.85
SEND_GLYPH = "↑"
STOP_GLYPH = "■"
HINT_IDLE = tr("Enter to send, Shift+Enter for a new line")
HINT_BUSY = tr("Working… press ■ to stop")


class PromptEdit(QPlainTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event: Any) -> None:
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        plain = not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if enter and plain:
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class Composer(QWidget):
    submitted = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        frame = QWidget()
        frame.setStyleSheet(
            f"background: {style.css_color(style.surface(palette))};"
            f"border: {style.HAIRLINE}px solid {style.css_color(style.hairline(palette))};"
            f"border-radius: {style.BUBBLE_RADIUS}px;"
        )
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(9, 7, 8, 7)
        inner.setSpacing(5)
        inner.addWidget(self._build_edit())
        inner.addLayout(self._build_footer(palette))
        column.addWidget(frame)

    def _build_edit(self) -> QPlainTextEdit:
        self._edit = PromptEdit()
        self._edit.setPlaceholderText(PLACEHOLDER)
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setStyleSheet("border: none; background: transparent;")
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._edit.setFixedHeight(MIN_HEIGHT)
        self._edit.submitted.connect(self._on_submit)
        self._edit.textChanged.connect(self._grow)
        return self._edit

    def _build_footer(self, palette) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._hint = QLabel(HINT_IDLE)
        font = self._hint.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * HINT_FONT_SCALE))
        self._hint.setFont(font)
        self._hint.setStyleSheet(f"color: {style.css_color(style.muted(palette))}; border: none;")
        row.addWidget(self._hint, 1)

        self._send = QPushButton(SEND_GLYPH)
        self._send.setFixedSize(SEND_SIZE, SEND_SIZE)
        self._send.setToolTip(tr("Send"))
        self._send.setStyleSheet(self._button_style(style.accent(palette)))
        self._send.clicked.connect(self._on_button)
        row.addWidget(self._send)
        return row

    def _button_style(self, fill) -> str:
        return (
            f"QPushButton {{ background: {style.css_color(fill)};"
            f"color: {style.css_color(self.palette().highlightedText().color())};"
            f"border: none; border-radius: {SEND_SIZE // 2}px; }}"
        )

    def _on_button(self) -> None:
        if self._busy:
            self.stopped.emit()
            return
        self._on_submit()

    def _grow(self) -> None:
        height = int(self._edit.document().size().height() * self._line_height()) + 12
        self._edit.setFixedHeight(max(MIN_HEIGHT, min(height, MAX_HEIGHT)))

    def _line_height(self) -> float:
        return self._edit.fontMetrics().lineSpacing()

    def _on_submit(self) -> None:
        if self._busy:
            return
        self.submitted.emit(self._edit.toPlainText().strip())

    def clear(self) -> None:
        self._edit.clear()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        palette = self.palette()
        self._send.setText(STOP_GLYPH if busy else SEND_GLYPH)
        self._send.setToolTip(tr("Stop") if busy else tr("Send"))
        self._send.setStyleSheet(self._button_style(style.danger(palette) if busy else style.accent(palette)))
        self._edit.setReadOnly(busy)
        self._hint.setText(HINT_BUSY if busy else HINT_IDLE)
