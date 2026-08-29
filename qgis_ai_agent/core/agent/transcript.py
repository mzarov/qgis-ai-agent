import json
from dataclasses import dataclass, field
from typing import Any

from qgis_ai_agent.core.llm.anthropic import THINKING_KEY
from qgis_ai_agent.core.llm.transport import PROTOCOL_NATIVE, ModelTurn, ToolCall
from qgis_ai_agent.qgis_tools.base import is_sensitive_egress

MAX_RESULT_CHARS = 4000
COMPACT_RESULT_CHARS = 500
KEEP_FULL_RESULTS = 6
TRUNCATION_NOTE = "… (result truncated)"
COMPACTION_NOTE = "… (older result compacted; re-run the tool if the details matter again)"
RESULTS_HEADER = "Tool results:"
EARLIER_IMAGE_NOTE = "[an earlier image was dropped to save space — render again if you need a fresh look]"
IMAGE_MEDIA = "image/png"
IMAGE_INTRO = "Image rendered by {tool}:"
IMAGE_OMITTED_NOTE = "[image omitted: this endpoint does not accept image input]"
SENSITIVE_RESULT_OMITTED = "[sensitive tool result omitted because sharing is disabled]"


@dataclass
class ToolResult:
    call: ToolCall
    payload: dict[str, Any]
    ok: bool = True
    image: str = ""
    egress: str = "metadata"

    @classmethod
    def failure(cls, call: ToolCall, error: str, egress: str = "metadata") -> "ToolResult":
        return cls(
            call=call,
            ok=False,
            payload={"error": error, "arguments_sent": call.arguments},
            egress=egress,
        )

    def to_text(self, limit: int = MAX_RESULT_CHARS) -> str:
        try:
            text = json.dumps(self.payload, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(self.payload)
        if len(text) > limit:
            note = COMPACTION_NOTE if limit < MAX_RESULT_CHARS else TRUNCATION_NOTE
            return text[:limit] + note
        return text


@dataclass
class Transcript:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.entries.append({"kind": "user", "text": text})

    def add_turn(self, turn: ModelTurn) -> None:
        turn.tool_calls = _unique_tool_calls(turn.tool_calls)
        self.entries.append({"kind": "turn", "turn": turn})

    def add_results(self, results: list[ToolResult], protocol: str) -> None:
        if results:
            self.entries.append({"kind": "results", "results": results, "protocol": protocol})

    def replace_results(self, results: list[ToolResult], protocol: str) -> None:
        remaining = {result.call.id: result for result in results}
        for entry in reversed(self.entries):
            if entry.get("kind") != "results":
                continue
            for index, existing in enumerate(entry["results"]):
                replacement = remaining.pop(existing.call.id, None)
                if replacement is not None:
                    entry["results"][index] = replacement
            if not remaining:
                return
        self.add_results(list(remaining.values()), protocol)

    def build_messages(
        self,
        system_prompt: str,
        history: list[dict[str, str]] | None = None,
        include_images: bool = True,
        allow_sensitive: bool = True,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        fresh_results = self._fresh_result_ids()
        last_image = self._last_image_id() if include_images else None
        for index, entry in enumerate(self.entries):
            messages.extend(
                self._render(
                    entry,
                    index in fresh_results,
                    index == last_image,
                    include_images,
                    allow_sensitive,
                )
            )
        return messages

    def _fresh_result_ids(self) -> set[int]:
        result_ids = [index for index, entry in enumerate(self.entries) if entry["kind"] == "results"]
        return set(result_ids[-KEEP_FULL_RESULTS:])

    def _last_image_id(self) -> int | None:
        for index in range(len(self.entries) - 1, -1, -1):
            entry = self.entries[index]
            if entry["kind"] == "results" and any(result.image for result in entry["results"]):
                return index
        return None

    @classmethod
    def _render(
        cls,
        entry: dict[str, Any],
        fresh: bool,
        carries_image: bool,
        images_allowed: bool,
        allow_sensitive: bool,
    ) -> list[dict[str, Any]]:
        kind = entry["kind"]
        if kind == "user":
            return [{"role": "user", "content": entry["text"]}]
        if kind == "turn":
            return [cls._render_turn(entry["turn"])]
        if kind == "results":
            return cls._render_results(
                entry["results"],
                entry["protocol"],
                fresh,
                carries_image,
                images_allowed,
                allow_sensitive,
            )
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
        if turn.thinking_blocks:
            message[THINKING_KEY] = turn.thinking_blocks
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
    def _render_results(
        cls,
        results: list[ToolResult],
        protocol: str,
        fresh: bool,
        carries_image: bool,
        images_allowed: bool,
        allow_sensitive: bool,
    ) -> list[dict[str, Any]]:
        limit = MAX_RESULT_CHARS if fresh else COMPACT_RESULT_CHARS
        if protocol == PROTOCOL_NATIVE:
            rendered = [
                {
                    "role": "tool",
                    "tool_call_id": result.call.id,
                    "content": cls._result_text(result, limit, allow_sensitive),
                }
                for result in results
            ]
        else:
            lines = [f"{result.call.name} -> {cls._result_text(result, limit, allow_sensitive)}" for result in results]
            rendered = [{"role": "user", "content": RESULTS_HEADER + "\n" + "\n".join(lines)}]
        for result in results:
            if not allow_sensitive and is_sensitive_egress(result.egress):
                continue
            attachment = cls._image_message(result, carries_image, images_allowed)
            if attachment is not None:
                rendered.append(attachment)
        return rendered

    @staticmethod
    def _result_text(result: ToolResult, limit: int, allow_sensitive: bool) -> str:
        if not allow_sensitive and is_sensitive_egress(result.egress):
            return SENSITIVE_RESULT_OMITTED
        return result.to_text(limit)

    @staticmethod
    def _image_message(result: ToolResult, carries_image: bool, images_allowed: bool) -> dict[str, Any] | None:
        if not result.image:
            return None
        intro = IMAGE_INTRO.format(tool=result.call.name)
        if not images_allowed:
            return {"role": "user", "content": f"{intro} {IMAGE_OMITTED_NOTE}"}
        if not carries_image:
            return {"role": "user", "content": f"{intro} {EARLIER_IMAGE_NOTE}"}
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


def _unique_tool_calls(calls: list[ToolCall]) -> list[ToolCall]:
    used: set[str] = set()
    prepared: list[ToolCall] = []
    for index, call in enumerate(calls, start=1):
        base = str(call.id or "").strip() or f"call_{index}"
        identifier = base
        suffix = 2
        while identifier in used:
            identifier = f"{base}_{suffix}"
            suffix += 1
        used.add(identifier)
        call.id = identifier
        prepared.append(call)
    return prepared
