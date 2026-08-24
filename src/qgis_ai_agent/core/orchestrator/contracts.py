from typing import Protocol


class PromptEditContract(Protocol):
    """Минимальный контракт поля ввода для очистки текста."""

    def clear(self) -> None:
        ...


class DockWidgetContract(Protocol):
    """Минимальный API UI для оркестратора."""

    prompt_edit: PromptEditContract

    def add_user_message(self, text: str) -> int:
        ...

    def add_system_message(self, text: str) -> int:
        ...

    def add_result_message(self, text: str) -> int:
        ...

    def add_plan_message(self, plan_lines: list[str]) -> int:
        ...

    def add_tool_message(self, text: str) -> int:
        ...

    def mark_tool_done(self, message_id: int, ok: bool = True) -> None:
        ...

    def mark_plan_completed(self, message_id: int) -> None:
        ...

    def set_confirm_visible(self, visible: bool) -> None:
        ...

    def set_busy(self, busy: bool) -> None:
        ...
