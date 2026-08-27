import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm.transport import PROTOCOL_NATIVE, ModelTurn, ToolCall

MAX_RESULT_CHARS = 4000
TRUNCATION_NOTE = "… (result truncated)"
RESULTS_HEADER = "Tool results:"
IMAGE_MEDIA = "image/png"
IMAGE_INTRO = "Image rendered by {tool}:"
IMAGE_OMITTED_NOTE = "[image omitted: this endpoint does not accept image input]"


@dataclass
class ToolResult:
    call: ToolCall
    payload: dict[str, Any]
    ok: bool = True
    image: str = ""

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
        include_images: bool = True,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        for entry in self.entries:
            messages.extend(self._render(entry, include_images))
        return messages

    @classmethod
    def _render(cls, entry: dict[str, Any], include_images: bool) -> list[dict[str, Any]]:
        kind = entry["kind"]
        if kind == "user":
            return [{"role": "user", "content": entry["text"]}]
        if kind == "turn":
            return [cls._render_turn(entry["turn"])]
        if kind == "results":
            return cls._render_results(entry["results"], entry["protocol"], include_images)
        return []

    @classmethod
    def _render_turn(cls, turn: ModelTurn) -> dict[str, Any]:
        if turn.protocol != PROTOCOL_NATIVE:
            payload = {
                "text": turn.text,
                "tool_calls": [{"name": call.name, "arguments": call.arguments} for call in turn.tool_calls],
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

    @classmethod
    def _render_results(cls, results: list[ToolResult], protocol: str, include_images: bool) -> list[dict[str, Any]]:
        if protocol == PROTOCOL_NATIVE:
            rendered = [
                {"role": "tool", "tool_call_id": result.call.id, "content": result.to_text()} for result in results
            ]
        else:
            lines = [f"{result.call.name} -> {result.to_text()}" for result in results]
            rendered = [{"role": "user", "content": RESULTS_HEADER + "\n" + "\n".join(lines)}]
        for result in results:
            attachment = cls._image_message(result, include_images)
            if attachment is not None:
                rendered.append(attachment)
        return rendered

    @staticmethod
    def _image_message(result: ToolResult, include_images: bool) -> dict[str, Any] | None:
        if not result.image:
            return None
        intro = IMAGE_INTRO.format(tool=result.call.name)
        if not include_images:
            return {"role": "user", "content": f"{intro} {IMAGE_OMITTED_NOTE}"}
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": intro},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{IMAGE_MEDIA};base64,{result.image}"},
                },
            ],
        }
