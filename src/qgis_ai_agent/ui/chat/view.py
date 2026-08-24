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


class ChatView(QWidget):
    """Вид чата с моделью сообщений и стабильным API для стриминга."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = ChatMessageModel(self)
        self._list = QListView(self)
        self._list.setModel(self._model)
        self._list.setUniformItemSizes(False)
        self._list.setWordWrap(True)
        edit_trigger = getattr(
            getattr(QAbstractItemView, "EditTrigger", QAbstractItemView),
            "NoEditTriggers",
            getattr(QAbstractItemView, "NoEditTriggers", 0),
        )
        selection_mode = getattr(
            getattr(QAbstractItemView, "SelectionMode", QAbstractItemView),
            "ExtendedSelection",
            getattr(QAbstractItemView, "ExtendedSelection", 3),
        )
        scroll_mode = getattr(
            getattr(QAbstractItemView, "ScrollMode", QAbstractItemView),
            "ScrollPerPixel",
            getattr(QAbstractItemView, "ScrollPerPixel", 0),
        )
        scroll_policy = getattr(
            getattr(Qt, "ScrollBarPolicy", Qt),
            "ScrollBarAlwaysOff",
            getattr(Qt, "ScrollBarAlwaysOff", 1),
        )
        self._list.setEditTriggers(edit_trigger)
        self._list.setSelectionMode(selection_mode)
        self._list.setVerticalScrollMode(scroll_mode)
        self._list.setHorizontalScrollBarPolicy(scroll_policy)
        self._list.setSpacing(4)
        self._list.setItemDelegate(ChatMessageDelegate(self._theme, self._list))
        self._list.viewport().installEventFilter(self)
        context_menu_policy = getattr(
            getattr(Qt, "ContextMenuPolicy", Qt),
            "CustomContextMenu",
            getattr(Qt, "CustomContextMenu", 3),
        )
        self._list.setContextMenuPolicy(context_menu_policy)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._list)
        copy_shortcut.activated.connect(self.copy_selected_messages)
        self._copy_shortcut = copy_shortcut

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._model.rowsInserted.connect(self._scroll_to_bottom)
        self._model.dataChanged.connect(self._scroll_to_bottom)

    def add_user_message(self, text: str) -> int:
        return self._model.add_message("user", text)

    def add_system_message(self, text: str) -> int:
        return self._model.add_message("system", text)

    def add_assistant_preface(self, text: str) -> int:
        return self._model.add_message("assistant_preface", text)

    def add_result_message(self, text: str) -> int:
        return self._model.add_message("result", text)

    def start_model_stream(self) -> int:
        return self._model.add_message("assistant", "…", streaming=True)

    def add_plan_message(self, plan_lines: list[str]) -> int:
        message_id = self._model.add_message("plan", "", streaming=False)
        self.finalize_model_plan(message_id, plan_lines)
        return message_id

    def append_model_chunk(self, message_id: int, chunk: str) -> None:
        current = self._model.message_text(message_id)
        if current == "…":
            self._model.replace_message(message_id, chunk, streaming=True)
            return
        self._model.append_to_message(message_id, chunk)

    def finalize_model_message(self, message_id: int, text: str) -> None:
        self._model.replace_message(message_id, text, streaming=False)

    def finalize_model_plan(self, message_id: int, plan_lines: list[str]) -> None:
        lines = [f"☐ {line}" for line in plan_lines if line.strip()]
        if lines:
            text = "План действий:\n" + "\n".join(lines)
        else:
            text = "План действий:\n…"
        self._model.replace_message(message_id, text, streaming=False, role="plan")

    def mark_plan_completed(self, message_id: int) -> None:
        text = self._model.message_text(message_id)
        if not text:
            return
        completed = text.replace("☐ ", "☑ ")
        self._model.replace_message(message_id, completed, streaming=False)

    def _theme(self):
        return build_theme_from_palette(self.palette())

    def _scroll_to_bottom(self, *args):
        self._list.scrollToBottom()

    def eventFilter(self, watched, event):
        if watched is self._list.viewport() and event.type() == QEvent.Type.Resize:
            self._list.doItemsLayout()
        return super().eventFilter(watched, event)

    def copy_selected_messages(self) -> None:
        indexes = self._list.selectionModel().selectedIndexes() if self._list.selectionModel() else []
        if not indexes:
            return
        rows = sorted(set(index.row() for index in indexes))
        texts = []
        for row in rows:
            idx = self._model.index(row, 0)
            role = idx.data(ChatMessageModel.ROLE_ROLE) or "system"
            text = idx.data(ChatMessageModel.ROLE_TEXT) or ""
            texts.append(f"[{role}] {text}")
        QGuiApplication.clipboard().setText("\n\n".join(texts))

    def copy_all_messages(self) -> None:
        messages = self._model.all_messages()
        if not messages:
            return
        text = "\n\n".join(f"[{msg.role}] {msg.text}" for msg in messages)
        QGuiApplication.clipboard().setText(text)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_selected = menu.addAction("Копировать выбранные сообщения")
        copy_all = menu.addAction("Копировать весь чат")
        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action == copy_selected:
            self.copy_selected_messages()
        elif action == copy_all:
            self.copy_all_messages()
