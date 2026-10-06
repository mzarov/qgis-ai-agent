from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import (
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_agent.i18n import tr
from ai_agent.ui import controls, style
from ai_agent.ui.activity import ActivityGroup
from ai_agent.ui.messages import AssistantMessage, SystemMessage, UserMessage
from ai_agent.ui.plan import PlanCard, PlanOffer
from ai_agent.ui.progress import ProgressLine
from ai_agent.ui.question import QuestionCard
from ai_agent.ui.thinking import ThinkingBlock
from ai_agent.ui.welcome import WelcomeCard

MESSAGE_SPACING = 11
WELCOME_STRETCH = 1
TAIL_STRETCH = 1
SIDE_PADDING = 12
PIN_TOLERANCE = 24


FEED_NAME = "feed"


class ConversationView(QScrollArea):
    confirm_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    plan_run_requested = pyqtSignal(str)
    rewind_requested = pyqtSignal(int)
    question_answered = pyqtSignal(str)
    suggestion_chosen = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"QScrollArea {{ background: {style.css_color(style.background(self.palette()))}; }}")

        # The viewport and the holder would otherwise paint the QGIS window colour over the backdrop.
        holder = QWidget()
        holder.setObjectName(FEED_NAME)
        style.fill(holder, style.background(self.palette()))
        self.viewport().setAutoFillBackground(False)
        self._column = QVBoxLayout(holder)
        self._column.setContentsMargins(SIDE_PADDING, SIDE_PADDING, SIDE_PADDING, SIDE_PADDING)
        self._column.setSpacing(MESSAGE_SPACING)
        # The working line is the feed's last row: every message goes in above it.
        self.progress = ProgressLine(self.palette())
        self._column.addWidget(self.progress)
        self._column.addStretch(1)
        self.setWidget(holder)

        self._pinned = True
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range_changed)
        bar.valueChanged.connect(self._on_value_changed)

        self._activity: ActivityGroup | None = None
        self._plan_offers: list[PlanOffer] = []
        self._questions: list[QuestionCard] = []
        self._draft: AssistantMessage | None = None
        self._thinking: ThinkingBlock | None = None
        self._entries: dict[int, object] = {}
        self._next_id = 1
        self._configured = True
        self._empty: QWidget | None = None
        self._show_welcome()

    def set_configured(self, configured: bool) -> None:
        if configured == self._configured:
            return
        self._configured = configured
        if self._empty is not None:
            self._drop_welcome()
            self._show_welcome()

    def _show_welcome(self) -> None:
        card = WelcomeCard(self._configured)
        card.suggestion_chosen.connect(self.suggestion_chosen.emit)
        card.settings_requested.connect(self.settings_requested.emit)
        self._empty = card
        self._insert(card, WELCOME_STRETCH)
        self._set_tail_stretch(0)

    def _drop_welcome(self) -> None:
        if self._empty is None:
            return
        self._discard(self._empty)
        self._empty = None
        self._set_tail_stretch(TAIL_STRETCH)

    def _discard(self, widget: QWidget) -> None:
        """Take a widget out of the feed now; Qt deletes it later.

        deleteLater alone leaves it laid out and painted until the event loop
        gets round to it — a busy main thread showed the welcome card drawn
        over a running conversation.
        """
        self._column.removeWidget(widget)
        widget.hide()
        widget.deleteLater()

    def _set_tail_stretch(self, stretch: int) -> None:
        self._column.setStretch(self._column.count() - 1, stretch)

    def add_user_message(self, text: str) -> int:
        # Any new message makes an earlier plan offer or question card stale.
        self._retire_plan_offers()
        self._retire_questions()
        self._close_activity()
        bubble = UserMessage(text)
        bubble.rewind_requested.connect(self.rewind_requested.emit)
        return self._append(bubble)

    def mark_rewind_point(self, entry_id: int, message: int) -> None:
        bubble = self._entries.get(entry_id)
        if isinstance(bubble, UserMessage):
            bubble.set_rewind_point(message)

    def add_assistant_message(self, markdown: str) -> int:
        self._close_activity()
        return self._append(AssistantMessage(markdown))

    def add_system_message(self, text: str) -> int:
        self._close_activity()
        return self._append(SystemMessage(text))

    def append_thinking(self, delta: str) -> None:
        if self._thinking is None:
            self._drop_draft()
            if self._activity is None:
                self._activity = ActivityGroup()
                self._append(self._activity)
            block = ThinkingBlock()
            self._activity.add_widget(block)
            self._activity.reveal()
            self._thinking = block
        self._thinking.append(delta)
        self._scroll_when_pinned()

    def _close_thinking(self) -> None:
        if self._thinking is None:
            return
        self._thinking.finish()
        self._thinking = None

    def append_draft(self, delta: str) -> None:
        if self._draft is None:
            draft = AssistantMessage("")
            self._append(draft)
            self._draft = draft
        self._draft.append(delta)
        self._scroll_when_pinned()

    def finish_draft(self, markdown: str) -> bool:
        draft = self._draft
        self._draft = None
        if draft is None:
            return False
        draft.set_markdown(markdown)
        self._close_activity()
        self._scroll_when_pinned()
        return True

    def keep_draft(self) -> str:
        """Keep a half-streamed answer when the run stops or fails; return its text."""
        draft = self._draft
        if draft is None:
            return ""
        text = draft.plain_text().strip()
        if not text:
            self._drop_draft()
            return ""
        self.finish_draft(text)
        return text

    def _drop_draft(self) -> None:
        if self._draft is None:
            return
        self._discard(self._draft)
        self._draft = None

    def add_activity_step(self, text: str) -> int:
        self._drop_draft()
        self._close_thinking()
        if self._activity is None:
            self._activity = ActivityGroup()
            self._append(self._activity)
        step = self._activity.add_step(text)
        self._scroll_when_pinned()
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

    def add_plan_card(self, steps: list[str], applies_itself: bool = False) -> int:
        self._close_activity()
        card = PlanCard(steps, applies_itself)
        card.confirmed.connect(self.confirm_requested.emit)
        card.cancelled.connect(self.cancel_requested.emit)
        return self._append(card)

    def add_plan_offer(self) -> int:
        self._retire_plan_offers()
        offer = PlanOffer(self.palette())
        self._plan_offers.append(offer)
        offer.run_requested.connect(self.plan_run_requested.emit)
        return self._append(offer)

    def add_question(self, question: str, options: list[str]) -> int:
        self._retire_questions()
        self._close_activity()
        card = QuestionCard(question, options, self.palette())
        self._questions.append(card)
        card.answered.connect(self.question_answered.emit)
        return self._append(card)

    def _retire_questions(self) -> None:
        for card in self._questions:
            card.retire()
        self._questions = []

    def _retire_plan_offers(self) -> None:
        for offer in self._plan_offers:
            offer.retire()
        self._plan_offers = []

    def mark_plan_applied(self, entry_id: int) -> None:
        card = self._entries.get(entry_id)
        if isinstance(card, PlanCard):
            card.mark_applied()

    def mark_plan_failed(self, entry_id: int) -> None:
        card = self._entries.get(entry_id)
        if isinstance(card, PlanCard):
            card.mark_failed()

    def mark_plan_cancelled(self, entry_id: int) -> None:
        card = self._entries.get(entry_id)
        if isinstance(card, PlanCard):
            card.mark_cancelled()

    def clear(self) -> None:
        for index in reversed(range(self._column.count())):
            widget = self._column.itemAt(index).widget()
            if widget is not None and widget is not self.progress:
                self._discard(widget)
        self._activity = None
        self._draft = None
        self._thinking = None
        self._plan_offers = []
        self._questions = []
        self._entries.clear()
        self._empty = None
        self._show_welcome()

    def copy_all(self) -> None:
        parts = []
        for index in range(self._column.count() - 1):
            widget = self._column.itemAt(index).widget()
            if isinstance(widget, (UserMessage, AssistantMessage, SystemMessage)):
                parts.append(widget.plain_text())
        text = "\n\n".join(part for part in parts if part)
        if text:
            QGuiApplication.clipboard().setText(text)

    def contextMenuEvent(self, event: Any) -> None:
        menu = controls.menu(self, self.palette())
        copy_action = menu.addAction(tr("Copy the whole conversation"))
        if menu.exec(event.globalPos()) == copy_action:
            self.copy_all()

    def _append(self, widget: QWidget) -> int:
        self._drop_draft()
        self._close_thinking()
        self._drop_welcome()
        self._insert(widget)
        self._scroll_when_pinned()
        return self._remember(widget)

    def _insert(self, widget: QWidget, stretch: int = 0) -> None:
        self._column.insertWidget(self._column.indexOf(self.progress), widget, stretch)

    def _remember(self, entry: object) -> int:
        entry_id = self._next_id
        self._next_id += 1
        self._entries[entry_id] = entry
        return entry_id

    def _close_activity(self) -> None:
        if self._activity is not None:
            self._activity.rest()
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

    def _scroll_when_pinned(self) -> None:
        if self._pinned:
            QTimer.singleShot(0, self._scroll_if_still_pinned)

    def _scroll_if_still_pinned(self) -> None:
        if self._pinned:
            self._scroll_to_bottom()
