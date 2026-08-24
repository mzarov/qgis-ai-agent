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

    def append_model_chunk(self, message_id: int, chunk: str) -> None:
        ...

    def start_model_stream(self) -> int:
        ...

    def finalize_model_message(self, message_id: int, text: str) -> None:
        ...

    def mark_plan_completed(self, message_id: int) -> None:
        ...

    def set_busy(self, busy: bool) -> None:
        ...
