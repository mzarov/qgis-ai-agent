import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm.transport import ModelTurn, ToolCall

# Предел длины сериализованного результата тула, чтобы не раздувать контекст.
MAX_RESULT_CHARS = 4000


@dataclass
class ToolResult:
    """Результат одного вызова тула, возвращаемый модели."""
    call: ToolCall
    payload: dict[str, Any]
    ok: bool = True

    def to_text(self) -> str:
        """Сериализует результат для сообщения модели."""
        try:
            text = json.dumps(self.payload, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(self.payload)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "… (результат обрезан)"
        return text


@dataclass
class Transcript:
    """
    Лента одного прогона агента: ходы модели и результаты вызовов.
    Плоская история чата пары «вызов ↔ результат» удержать не может,
    поэтому прогон живёт в собственной структуре.
    """
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        """Добавляет реплику пользователя."""
        self.entries.append({"kind": "user", "text": text})

    def add_turn(self, turn: ModelTurn) -> None:
        """Добавляет ход модели вместе с запрошенными вызовами."""
        self.entries.append({"kind": "turn", "turn": turn})

    def add_results(self, results: list[ToolResult], protocol: str) -> None:
        """Добавляет результаты вызовов, полученные на предыдущем ходе."""
        if results:
            self.entries.append({"kind": "results", "results": results, "protocol": protocol})

    def build_messages(self, system_prompt: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        """Собирает массив messages для API из системного промпта, истории и ленты."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        for entry in self.entries:
            kind = entry["kind"]
            if kind == "user":
                messages.append({"role": "user", "content": entry["text"]})
            elif kind == "turn":
                messages.append(self._render_turn(entry["turn"]))
            elif kind == "results":
                messages.extend(self._render_results(entry["results"], entry["protocol"]))
        return messages

    @staticmethod
    def _render_turn(turn: ModelTurn) -> dict[str, Any]:
        """Превращает ход модели в assistant-сообщение нужного протокола."""
        if turn.protocol == "native":
            message: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
            if turn.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in turn.tool_calls
                ]
            return message
        # JSON-протокол: восстанавливаем управляющий объект как обычный текст.
        payload = {
            "text": turn.text,
            "tool_calls": [
                {"name": call.name, "arguments": call.arguments} for call in turn.tool_calls
            ],
        }
        return {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}

    @staticmethod
    def _render_results(results: list[ToolResult], protocol: str) -> list[dict[str, Any]]:
        """Превращает результаты вызовов в сообщения нужного протокола."""
        if protocol == "native":
            return [
                {
                    "role": "tool",
                    "tool_call_id": result.call.id,
                    "content": result.to_text(),
                }
                for result in results
            ]
        # Без нативных tool_calls результаты возвращаются обычной репликой.
        lines = [f"{result.call.name} -> {result.to_text()}" for result in results]
        return [{"role": "user", "content": "Результаты вызовов:\n" + "\n".join(lines)}]
