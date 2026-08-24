from dataclasses import dataclass

from qgis.PyQt.QtCore import QAbstractListModel, QModelIndex, Qt


@dataclass
class ChatMessage:
    message_id: int
    role: str
    text: str


class ChatMessageModel(QAbstractListModel):
    _ITEM_DATA_ROLE = getattr(Qt, "ItemDataRole", Qt)
    _DISPLAY_ROLE = getattr(_ITEM_DATA_ROLE, "DisplayRole", getattr(Qt, "DisplayRole", 0))
    _USER_ROLE = int(getattr(_ITEM_DATA_ROLE, "UserRole", getattr(Qt, "UserRole", 32)))

    ROLE_ID = _USER_ROLE + 1
    ROLE_ROLE = _USER_ROLE + 2
    ROLE_TEXT = _USER_ROLE + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: list[ChatMessage] = []
        self._next_id = 1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._messages)

    def data(self, index: QModelIndex, role: int = _DISPLAY_ROLE):
        if not index.isValid():
            return None
        message = self._messages[index.row()]
        if role in (self._DISPLAY_ROLE, self.ROLE_TEXT):
            return message.text
        if role == self.ROLE_ID:
            return message.message_id
        if role == self.ROLE_ROLE:
            return message.role
        return None

    def roleNames(self):
        return {
            self.ROLE_ID: b"message_id",
            self.ROLE_ROLE: b"role",
            self.ROLE_TEXT: b"text",
        }

    def add_message(self, role: str, text: str) -> int:
        message_id = self._next_id
        self._next_id += 1
        row = len(self._messages)
        self.beginInsertRows(QModelIndex(), row, row)
        self._messages.append(ChatMessage(message_id, role, text))
        self.endInsertRows()
        return message_id

    def replace_message(self, message_id: int, text: str, role: str | None = None) -> None:
        row = self._row_by_id(message_id)
        if row < 0:
            return
        self._messages[row].text = text
        if role is not None:
            self._messages[row].role = role
        index = self.index(row, 0)
        self.dataChanged.emit(
            index, index, [self._DISPLAY_ROLE, self.ROLE_TEXT, self.ROLE_ROLE]
        )

    def message_text(self, message_id: int) -> str:
        row = self._row_by_id(message_id)
        return self._messages[row].text if row >= 0 else ""

    def all_messages(self) -> list[ChatMessage]:
        return list(self._messages)

    def _row_by_id(self, message_id: int) -> int:
        for row, message in enumerate(self._messages):
            if message.message_id == message_id:
                return row
        return -1
