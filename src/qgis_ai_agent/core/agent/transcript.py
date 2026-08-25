import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm.transport import PROTOCOL_NATIVE, ModelTurn, ToolCall

MAX_RESULT_CHARS = 4000
TRUNCATION_NOTE = "… (результат обрезан)"
RESULTS_HEADER = "Результаты вызовов:"


@dataclass
class ToolResult:
    call: ToolCall
    payload: dict[str, Any]
    ok: bool = True

    @classmethod
    def failure(cls, call: ToolCall, error: str) -> "ToolResult":
        return cls(
            call=call,
            ok=False,
            payload={"error": error, "arguments_sent": call.arguments},
        )

    def to_text(self) -> str:
        try:
            text = json.dumps(self.payload, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(self.payload)
        if len(text) > MAX_RESULT_CHARS:
            return text[:MAX_RESULT_CHARS] + TRUNCATION_NOTE
        return text


@dataclass
class Transcript:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.entries.append({"kind": "user", "text": text})

    def add_turn(self, turn: ModelTurn) -> None:
        self.entries.append({"kind": "turn", "turn": turn})

    def add_results(self, results: list[ToolResult], protocol: str) -> None:
        if results:
            self.entries.append({"kind": "results", "results": results, "protocol": protocol})

    def build_messages(
        self,
        system_prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        for entry in self.entries:
            messages.extend(self._render(entry))
        return messages

    @classmethod
    def _render(cls, entry: dict[str, Any]) -> list[dict[str, Any]]:
        kind = entry["kind"]
        if kind == "user":
            return [{"role": "user", "content": entry["text"]}]
        if kind == "turn":
            return [cls._render_turn(entry["turn"])]
        if kind == "results":
            return cls._render_results(entry["results"], entry["protocol"])
        return []

    @classmethod
    def _render_turn(cls, turn: ModelTurn) -> dict[str, Any]:
        if turn.protocol != PROTOCOL_NATIVE:
            payload = {
                "text": turn.text,
                "tool_calls": [
                    {"name": call.name, "arguments": call.arguments} for call in turn.tool_calls
                ],
            }
            return {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}

        message: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
        if turn.tool_calls:
            message["tool_calls"] = [cls._render_call(call) for call in turn.tool_calls]
        return message

    @staticmethod
    def _render_call(call: ToolCall) -> dict[str, Any]:
        return {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments, ensure_ascii=False),
            },
        }

    @staticmethod
    def _render_results(results: list[ToolResult], protocol: str) -> list[dict[str, Any]]:
        if protocol == PROTOCOL_NATIVE:
            return [
                {"role": "tool", "tool_call_id": result.call.id, "content": result.to_text()}
                for result in results
            ]
        lines = [f"{result.call.name} -> {result.to_text()}" for result in results]
        return [{"role": "user", "content": RESULTS_HEADER + "\n" + "\n".join(lines)}]
