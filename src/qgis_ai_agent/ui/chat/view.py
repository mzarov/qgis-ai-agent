from qgis.PyQt.QtCore import QEvent, Qt
from qgis.PyQt.QtGui import QGuiApplication, QKeySequence
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QListView,
    QMenu,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from qgis_ai_agent.ui.chat.delegate import ChatMessageDelegate
from qgis_ai_agent.ui.chat.model import ChatMessageModel
from qgis_ai_agent.ui.chat.theme import build_theme_from_palette

ITEM_SPACING = 4
PENDING_MARKER = "⏳"
REJECTED_MARKER = "⊘"
DONE_MARKER = "✓"
FAILED_MARKER = "✕"
PLAN_HEADER = "План действий:"
PLAN_PENDING = "☐ "
PLAN_DONE = "☑ "


def _enum(owner, group: str, name: str, fallback):
    return getattr(getattr(owner, group, owner), name, getattr(owner, name, fallback))


class ChatView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = ChatMessageModel(self)
        self._list = QListView(self)
        self._configure_list()
        self._install_shortcuts()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._model.rowsInserted.connect(self._scroll_to_bottom)
        self._model.dataChanged.connect(self._scroll_to_bottom)

    def _configure_list(self) -> None:
        self._list.setModel(self._model)
        self._list.setUniformItemSizes(False)
        self._list.setWordWrap(True)
        self._list.setEditTriggers(
            _enum(QAbstractItemView, "EditTrigger", "NoEditTriggers", 0)
        )
        self._list.setSelectionMode(
            _enum(QAbstractItemView, "SelectionMode", "ExtendedSelection", 3)
        )
        self._list.setVerticalScrollMode(
            _enum(QAbstractItemView, "ScrollMode", "ScrollPerPixel", 0)
        )
        self._list.setHorizontalScrollBarPolicy(
            _enum(Qt, "ScrollBarPolicy", "ScrollBarAlwaysOff", 1)
        )
        self._list.setSpacing(ITEM_SPACING)
        self._list.setItemDelegate(ChatMessageDelegate(self._theme, self._list))
        self._list.viewport().installEventFilter(self)
        self._list.setContextMenuPolicy(
            _enum(Qt, "ContextMenuPolicy", "CustomContextMenu", 3)
        )
        self._list.customContextMenuRequested.connect(self._show_context_menu)

    def _install_shortcuts(self) -> None:
        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._list)
        self._copy_shortcut.activated.connect(self.copy_selected_messages)

    def add_user_message(self, text: str) -> int:
        return self._model.add_message("user", text)

    def add_system_message(self, text: str) -> int:
        return self._model.add_message("system", text)

    def add_result_message(self, text: str) -> int:
        return self._model.add_message("result", text)

    def add_tool_message(self, text: str) -> int:
        return self._model.add_message("tool", f"{PENDING_MARKER} {text}")

    def add_rejected_message(self, text: str) -> int:
        return self._model.add_message("tool", f"{REJECTED_MARKER} {text}")

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        text = self._model.message_text(message_id)
        if not text:
            return
        marker = DONE_MARKER if ok else FAILED_MARKER
        self._model.replace_message(message_id, text.replace(PENDING_MARKER, marker, 1))

    def add_plan_message(self, plan_lines: list[str]) -> int:
        lines = [f"{PLAN_PENDING}{line}" for line in plan_lines if line.strip()]
        body = "\n".join(lines) if lines else "…"
        return self._model.add_message("plan", f"{PLAN_HEADER}\n{body}")

    def mark_plan_completed(self, message_id: int) -> None:
        text = self._model.message_text(message_id)
        if text:
            self._model.replace_message(message_id, text.replace(PLAN_PENDING, PLAN_DONE))

    def copy_selected_messages(self) -> None:
        selection = self._list.selectionModel()
        indexes = selection.selectedIndexes() if selection else []
        if not indexes:
            return
        rows = sorted({index.row() for index in indexes})
        texts = [self._format_row(row) for row in rows]
        QGuiApplication.clipboard().setText("\n\n".join(texts))

    def copy_all_messages(self) -> None:
        messages = self._model.all_messages()
        if not messages:
            return
        text = "\n\n".join(f"[{message.role}] {message.text}" for message in messages)
        QGuiApplication.clipboard().setText(text)

    def eventFilter(self, watched, event):
        if watched is self._list.viewport() and event.type() == QEvent.Type.Resize:
            self._list.doItemsLayout()
        return super().eventFilter(watched, event)

    def _format_row(self, row: int) -> str:
        index = self._model.index(row, 0)
        role = index.data(ChatMessageModel.ROLE_ROLE) or "system"
        text = index.data(ChatMessageModel.ROLE_TEXT) or ""
        return f"[{role}] {text}"

    def _theme(self):
        return build_theme_from_palette(self.palette())

    def _scroll_to_bottom(self, *args) -> None:
        self._list.scrollToBottom()

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_selected = menu.addAction("Копировать выбранные сообщения")
        copy_all = menu.addAction("Копировать весь чат")
        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action == copy_selected:
            self.copy_selected_messages()
        elif action == copy_all:
            self.copy_all_messages()
