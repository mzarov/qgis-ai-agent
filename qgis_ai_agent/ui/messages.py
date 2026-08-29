from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget

from qgis_ai_agent.ui import style

USER_MAX_WIDTH_RATIO = 0.82
BUBBLE_PADDING = 8
BUBBLE_SIDE_PADDING = 11
BROWSER_EXTRA_HEIGHT = 6
WRAP_SLACK = 10
SYSTEM_FONT_SCALE = 0.92
REPAINT_INTERVAL_MS = 80


class UserMessage(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        palette = self.palette()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            f"background: {style.css_color(style.user_bubble(palette))};"
            f"color: {style.css_color(style.text(palette))};"
            f"border-radius: {style.BUBBLE_RADIUS}px;"
            f"padding: {BUBBLE_PADDING}px {BUBBLE_SIDE_PADDING}px;"
        )
        row.addWidget(label, 0)
        self._label = label

    def resizeEvent(self, event: Any) -> None:
        self._fit()
        super().resizeEvent(event)

    def _fit(self) -> None:
        metrics = self._label.fontMetrics()
        lines = self._label.text().split("\n") or [""]
        natural = max(_line_width(metrics, line) for line in lines)
        limit = int(self.width() * USER_MAX_WIDTH_RATIO)
        self._label.setFixedWidth(min(natural + BUBBLE_SIDE_PADDING * 2 + WRAP_SLACK, limit))


class AssistantMessage(QWidget):
    def __init__(self, markdown: str, parent=None):
        super().__init__(parent)
        palette = self.palette()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setFrameShape(QFrame.Shape.NoFrame)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setStyleSheet(f"background: transparent; color: {style.css_color(style.text(palette))}; border: none;")
        self._apply_markdown(browser, markdown)
        browser.document().documentLayout().documentSizeChanged.connect(lambda _: self._fit(browser))
        column.addWidget(browser)
        self._browser = browser
        self._markdown = markdown
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(REPAINT_INTERVAL_MS)
        self._repaint.timeout.connect(self._render)

    def append(self, delta: str) -> None:
        self._markdown += delta
        if not self._repaint.isActive():
            self._repaint.start()

    def set_markdown(self, markdown: str) -> None:
        self._repaint.stop()
        self._markdown = markdown
        self._render()

    def _render(self) -> None:
        self._apply_markdown(self._browser, self._markdown)
        self._fit(self._browser)

    @staticmethod
    def _apply_markdown(browser: QTextBrowser, markdown: str) -> None:
        document = browser.document()
        document.setDocumentMargin(0)
        try:
            document.setMarkdown(markdown)
        except AttributeError:
            browser.setPlainText(markdown)

    def _fit(self, browser: QTextBrowser) -> None:
        document = browser.document()
        document.setTextWidth(max(1, browser.viewport().width()))
        browser.setFixedHeight(int(document.size().height()) + BROWSER_EXTRA_HEIGHT)

    def resizeEvent(self, event: Any) -> None:
        self._fit(self._browser)
        super().resizeEvent(event)


class SystemMessage(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        palette = self.palette()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = label.font()
        font.setPointSizeF(max(1.0, font.pointSizeF() * SYSTEM_FONT_SCALE))
        label.setFont(font)
        label.setStyleSheet(
            f"color: {style.css_color(style.muted(palette))};"
            f"border-left: 2px solid {style.css_color(style.hairline(palette))};"
            "padding: 2px 0 2px 9px;"
        )
        row.addWidget(label, 1)


def _line_width(metrics: Any, line: str) -> int:
    advance = metrics.horizontalAdvance(line)
    try:
        painted = metrics.boundingRect(line).width()
    except Exception:
        painted = 0
    return max(int(advance), int(painted))
