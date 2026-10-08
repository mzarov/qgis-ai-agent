from typing import Any

from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QTextBrowser, QToolButton, QVBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import icons, style

USER_MAX_WIDTH_RATIO = 0.86
BUBBLE_PADDING = 8
BUBBLE_SIDE_PADDING = 12
# The bubble's corner nearest the composer is tighter: it points back at where the message came from.
BUBBLE_TAIL_RADIUS = 3
BROWSER_EXTRA_HEIGHT = 6
WRAP_SLACK = 10
SYSTEM_FONT_SCALE = 0.92
REPAINT_INTERVAL_MS = 80
REWIND_ICON = 14
REWIND_BUTTON = 24
REWIND = tr("Rewind to before this message")


class UserMessage(QWidget):
    """The user's bubble; with a place in the conversation it offers a rewind button on hover."""

    rewind_requested = pyqtSignal(int)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        palette = self.palette()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self.message: int | None = None
        self.rewind = _rewind_button(palette)
        self.rewind.clicked.connect(self._ask_rewind)
        row.addWidget(self.rewind, 0, Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            f"background: {style.css_color(style.user_bubble(palette))};"
            f"color: {style.css_color(style.text(palette))};"
            f"border-radius: {style.BUBBLE_RADIUS}px;"
            f"border-bottom-right-radius: {BUBBLE_TAIL_RADIUS}px;"
            f"padding: {BUBBLE_PADDING}px {BUBBLE_SIDE_PADDING}px;"
        )
        row.addWidget(label, 0)
        self._label = label

    def plain_text(self) -> str:
        return self._label.text()

    def set_rewind_point(self, message: int) -> None:
        self.message = message

    def _ask_rewind(self) -> None:
        if self.message is not None:
            self.rewind_requested.emit(self.message)

    def enterEvent(self, event: Any) -> None:
        self.rewind.setVisible(self.message is not None)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        self.rewind.setVisible(False)
        super().leaveEvent(event)

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

    def plain_text(self) -> str:
        return self._markdown

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
        style.scale_font(label, SYSTEM_FONT_SCALE)
        label.setStyleSheet(
            f"color: {style.css_color(style.muted(palette))};"
            f"border-left: 2px solid {style.css_color(style.hairline(palette))};"
            "padding: 2px 0 2px 9px;"
        )
        row.addWidget(label, 1)
        self._label = label

    def plain_text(self) -> str:
        return self._label.text()


def _line_width(metrics: Any, line: str) -> int:
    advance = metrics.horizontalAdvance(line)
    try:
        painted = metrics.boundingRect(line).width()
    except Exception:
        painted = 0
    return max(int(advance), int(painted))


def _rewind_button(palette: Any) -> QToolButton:
    button = QToolButton()
    button.setFixedSize(REWIND_BUTTON, REWIND_BUTTON)
    button.setAutoRaise(True)
    button.setToolTip(REWIND)
    button.setAccessibleName(REWIND)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        "QToolButton { border: none; background: transparent; border-radius: 6px; }"
        f"QToolButton:hover {{ background: {style.css_color(style.elevated(palette))}; }}"
    )
    icon = icons.drawn("rewind", style.muted(palette), REWIND_ICON)
    if icon is None:
        button.setText("↶")
    else:
        button.setIcon(icon)
        button.setIconSize(QSize(REWIND_ICON, REWIND_ICON))
    # Hidden until hover, but its room is kept so the bubble does not jump sideways.
    policy = button.sizePolicy()
    policy.setRetainSizeWhenHidden(True)
    button.setSizePolicy(policy)
    button.setVisible(False)
    return button
