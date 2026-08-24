from dataclasses import dataclass

from qgis.PyQt.QtCore import QAbstractListModel, QModelIndex, Qt


@dataclass
class ChatMessage:
    """Сообщение чата в модели."""
    message_id: int
    role: str
    text: str
    streaming: bool = False


class ChatMessageModel(QAbstractListModel):
    """Модель сообщений чата для QListView."""
    _ITEM_DATA_ROLE = getattr(Qt, "ItemDataRole", Qt)
    _DISPLAY_ROLE = getattr(_ITEM_DATA_ROLE, "DisplayRole", getattr(Qt, "DisplayRole", 0))
    _USER_ROLE = int(getattr(_ITEM_DATA_ROLE, "UserRole", getattr(Qt, "UserRole", 32)))

    ROLE_ID = _USER_ROLE + 1
    ROLE_ROLE = _USER_ROLE + 2
    ROLE_TEXT = _USER_ROLE + 3
    ROLE_STREAMING = _USER_ROLE + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: list[ChatMessage] = []
        self._next_id = 1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._messages)

    def data(self, index: QModelIndex, role: int = _DISPLAY_ROLE):
        if not index.isValid():
            return None
        msg = self._messages[index.row()]
        if role in (self._DISPLAY_ROLE, self.ROLE_TEXT):
            return msg.text
        if role == self.ROLE_ID:
            return msg.message_id
        if role == self.ROLE_ROLE:
            return msg.role
        if role == self.ROLE_STREAMING:
            return msg.streaming
        return None

    def roleNames(self):
        return {
            self.ROLE_ID: b"message_id",
            self.ROLE_ROLE: b"role",
            self.ROLE_TEXT: b"text",
            self.ROLE_STREAMING: b"streaming",
        }

    def add_message(self, role: str, text: str, streaming: bool = False) -> int:
        """Добавляет новое сообщение и возвращает его ID."""
        msg_id = self._next_id
        self._next_id += 1
        row = len(self._messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(ChatMessage(msg_id, role, text, streaming))
        self.endInsertRows()
        return msg_id

    def append_to_message(self, message_id: int, chunk: str) -> None:
        """Дописывает фрагмент текста к сообщению."""
        row = self._row_by_id(message_id)
        if row < 0:
            return
        self._messages[row].text += chunk
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self._DISPLAY_ROLE, self.ROLE_TEXT])

    def replace_message(
        self,
        message_id: int,
        text: str,
        streaming: bool = False,
        role: str | None = None,
    ) -> None:
        """Полностью заменяет текст сообщения."""
        row = self._row_by_id(message_id)
        if row < 0:
            return
        self._messages[row].text = text
        self._messages[row].streaming = streaming
        if role is not None:
            self._messages[row].role = role
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx,
            idx,
            [self._DISPLAY_ROLE, self.ROLE_TEXT, self.ROLE_STREAMING, self.ROLE_ROLE],
        )

    def message_text(self, message_id: int) -> str:
        """Возвращает текст сообщения по ID."""
        row = self._row_by_id(message_id)
        if row < 0:
            return ""
        return self._messages[row].text

    def _row_by_id(self, message_id: int) -> int:
        for i, msg in enumerate(self._messages):
            if msg.message_id == message_id:
                return i
        return -1

    def all_messages(self) -> list[ChatMessage]:
        """Возвращает копию списка сообщений для экспорта/копирования."""
        return list(self._messages)
