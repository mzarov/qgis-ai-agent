from typing import Any

from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import (
    QFrame,
    QLabel,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui import style
from qgis_ai_agent.ui.activity import ActivityGroup
from qgis_ai_agent.ui.messages import AssistantMessage, SystemMessage, UserMessage
from qgis_ai_agent.ui.plan import PlanCard

MESSAGE_SPACING = 11
SIDE_PADDING = 12
PIN_TOLERANCE = 24
EMPTY_HINT = "Спросите про проект или попросите обработать слои."


class ConversationView(QScrollArea):
    confirm_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QScrollArea {{ background: {style.css_color(style.surface(self.palette()))}; }}"
        )

        holder = QWidget()
        self._column = QVBoxLayout(holder)
        self._column.setContentsMargins(SIDE_PADDING, SIDE_PADDING, SIDE_PADDING, SIDE_PADDING)
        self._column.setSpacing(MESSAGE_SPACING)
        self._column.addStretch(1)
        self.setWidget(holder)

        self._pinned = True
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range_changed)
        bar.valueChanged.connect(self._on_value_changed)

        self._activity: ActivityGroup | None = None
        self._entries: dict[int, object] = {}
        self._next_id = 1
        self._empty = self._build_hint()
        self._insert(self._empty)

    def _build_hint(self) -> QLabel:
        label = QLabel(EMPTY_HINT)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {style.css_color(style.muted(self.palette()))};")
        return label

    def add_user_message(self, text: str) -> int:
        self._close_activity()
        return self._append(UserMessage(text))

    def add_assistant_message(self, markdown: str) -> int:
        self._close_activity()
        return self._append(AssistantMessage(markdown))

    def add_system_message(self, text: str) -> int:
        self._close_activity()
        return self._append(SystemMessage(text))

    def add_activity_step(self, text: str) -> int:
        if self._activity is None:
            self._activity = ActivityGroup()
            self._append(self._activity)
        step = self._activity.add_step(text)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return self._remember(step)

    def mark_activity_step(self, entry_id: int, ok: bool) -> None:
        label = self._entries.get(entry_id)
        if label is not None and self._activity is not None:
            self._activity.mark_step(label, ok)

    def add_rejected_step(self, text: str) -> int:
        entry_id = self.add_activity_step(text)
        label = self._entries.get(entry_id)
        if label is not None and self._activity is not None:
            self._activity.mark_rejected(label)
        return entry_id

    def add_plan_card(self, steps: list[str]) -> int:
        self._close_activity()
        card = PlanCard(steps)
        card.confirmed.connect(self.confirm_requested.emit)
        card.cancelled.connect(self.cancel_requested.emit)
        return self._append(card)

    def mark_plan_applied(self, entry_id: int) -> None:
        card = self._entries.get(entry_id)
        if isinstance(card, PlanCard):
            card.mark_applied()

    def mark_plan_cancelled(self, entry_id: int) -> None:
        card = self._entries.get(entry_id)
        if isinstance(card, PlanCard):
            card.mark_cancelled()

    def clear(self) -> None:
        while self._column.count() > 1:
            item = self._column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._activity = None
        self._entries.clear()
        self._empty = self._build_hint()
        self._insert(self._empty)

    def copy_all(self) -> None:
        parts = []
        for index in range(self._column.count() - 1):
            widget = self._column.itemAt(index).widget()
            if isinstance(widget, (UserMessage, AssistantMessage, SystemMessage)):
                parts.append(widget.findChild(QLabel).text() if widget.findChild(QLabel) else "")
        text = "\n\n".join(part for part in parts if part)
        if text:
            QGuiApplication.clipboard().setText(text)

    def contextMenuEvent(self, event: Any) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Копировать весь диалог")
        if menu.exec(event.globalPos()) == copy_action:
            self.copy_all()

    def _append(self, widget: QWidget) -> int:
        if self._empty is not None:
            self._empty.deleteLater()
            self._empty = None
        self._insert(widget)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return self._remember(widget)

    def _insert(self, widget: QWidget) -> None:
        self._column.insertWidget(self._column.count() - 1, widget)

    def _remember(self, entry: object) -> int:
        entry_id = self._next_id
        self._next_id += 1
        self._entries[entry_id] = entry
        return entry_id

    def _close_activity(self) -> None:
        self._activity = None

    def _on_value_changed(self, value: int) -> None:
        self._pinned = value >= self.verticalScrollBar().maximum() - PIN_TOLERANCE

    def _on_range_changed(self, minimum: int, maximum: int) -> None:
        if self._pinned:
            self.verticalScrollBar().setValue(maximum)

    def _scroll_to_bottom(self) -> None:
        self._pinned = True
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
