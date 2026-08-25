class HistoryStore:

    def __init__(self, max_messages: int = 12):
        self._max_messages = max_messages
        self._messages: list[dict[str, str]] = []

    def add(self, role: str, content: str) -> None:
        if not content.strip():
            return
        self._messages.append({"role": role, "content": content.strip()})
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages :]

    def get(self) -> list[dict[str, str]]:
        return list(self._messages)
