import json
from collections.abc import Callable
from typing import Any

from ai_agent.core.llm.anthropic import TEXT_BLOCK, THINKING_BLOCK, TOOL_USE
from ai_agent.core.llm.client import ApiResponseError, post_json
from ai_agent.core.llm.dialects import resolve
from ai_agent.core.llm.refusals import streaming_unsupported, thinking_unsupported
from ai_agent.core.llm.stream import SseAccumulator
from ai_agent.core.llm.stream_runner import post_stream
from ai_agent.core.settings import (
    get_dialect,
    get_model,
    get_supports_streaming,
    set_supports_streaming,
)

MESSAGE_START = "message_start"
MESSAGE_DELTA = "message_delta"
BLOCK_START = "content_block_start"
BLOCK_DELTA = "content_block_delta"
BLOCK_STOP = "content_block_stop"
TEXT_DELTA = "text_delta"
THINKING_DELTA = "thinking_delta"
SIGNATURE_DELTA = "signature_delta"
INPUT_JSON_DELTA = "input_json_delta"
SIGNATURE = "signature"
PARTIAL_JSON = "partial_json"


class StreamedMessage:
    def __init__(
        self,
        on_text: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
    ):
        self._on_text = on_text
        self._on_thinking = on_thinking
        self._blocks: dict[int, dict[str, Any]] = {}
        self._json: dict[int, list[str]] = {}
        self._stop_reason = ""
        self._usage: dict[str, Any] = {}

    def take(self, event: str) -> None:
        try:
            parsed = json.loads(event)
        except ValueError:
            return
        kind = parsed.get("type")
        if kind == MESSAGE_START:
            self._merge_usage((parsed.get("message") or {}).get("usage"))
        elif kind == BLOCK_START:
            self._start_block(parsed)
        elif kind == BLOCK_DELTA:
            self._take_delta(parsed)
        elif kind == BLOCK_STOP:
            self._close_block(parsed)
        elif kind == MESSAGE_DELTA:
            self._stop_reason = str((parsed.get("delta") or {}).get("stop_reason") or self._stop_reason)
            self._merge_usage(parsed.get("usage"))

    def _merge_usage(self, usage: Any) -> None:
        if isinstance(usage, dict):
            self._usage.update(usage)

    def _start_block(self, parsed: dict[str, Any]) -> None:
        index = int(parsed.get("index") or 0)
        block = dict(parsed.get("content_block") or {})
        if block.get("type") == TOOL_USE:
            block["input"] = {}
            self._json[index] = []
        self._blocks[index] = block

    def _take_delta(self, parsed: dict[str, Any]) -> None:
        index = int(parsed.get("index") or 0)
        delta = parsed.get("delta") or {}
        block = self._blocks.get(index)
        if block is None:
            return
        kind = delta.get("type")
        if kind == TEXT_DELTA:
            self._grow(block, TEXT_BLOCK, delta.get("text"))
            if self._on_text is not None and not self._json:
                self._on_text(str(delta.get("text") or ""))
        elif kind == THINKING_DELTA:
            self._grow(block, THINKING_BLOCK, delta.get(THINKING_BLOCK))
            if self._on_thinking is not None:
                self._on_thinking(str(delta.get(THINKING_BLOCK) or ""))
        elif kind == SIGNATURE_DELTA:
            self._grow(block, SIGNATURE, delta.get(SIGNATURE))
        elif kind == INPUT_JSON_DELTA:
            self._json.setdefault(index, []).append(str(delta.get(PARTIAL_JSON) or ""))

    @staticmethod
    def _grow(block: dict[str, Any], key: str, addition: Any) -> None:
        if addition:
            block[key] = str(block.get(key) or "") + str(addition)

    def _close_block(self, parsed: dict[str, Any]) -> None:
        index = int(parsed.get("index") or 0)
        block = self._blocks.get(index)
        if block is None or block.get("type") != TOOL_USE:
            return
        block["input"] = _as_object("".join(self._json.get(index) or []))

    def response(self) -> dict[str, Any]:
        return {
            "content": [block for _, block in sorted(self._blocks.items())],
            "stop_reason": self._stop_reason,
            "usage": self._usage,
        }


class AnthropicExchange:
    def __init__(
        self,
        endpoint: str,
        headers: dict[str, str],
        timeout: int,
        url: str,
        overrides: dict[str, Any],
        on_chunk: Any,
        on_thinking: Any,
    ):
        self._endpoint = endpoint
        self._headers = headers
        self._timeout = timeout
        self._url = url
        self._verify = overrides.get("verify_override")
        overridden_model = overrides.get("model_override")
        self._model = (overridden_model if overridden_model is not None else get_model()) or ""
        chosen = overrides.get("dialect_override")
        self._dialect = resolve(url, chosen if chosen is not None else get_dialect())
        self._feedback = overrides.get("feedback_override")
        self._on_chunk = on_chunk
        self._on_thinking = on_thinking

    def send(self, body: dict[str, Any]) -> dict[str, Any]:
        streamed = self._streamed(body)
        if streamed is not None:
            return streamed
        return post_json(
            self._endpoint,
            self._headers,
            body,
            self._timeout,
            self._verify,
            self._feedback,
        )

    def _streamed(self, body: dict[str, Any]) -> dict[str, Any] | None:
        if self._on_chunk is None or get_supports_streaming(self._url, self._model, self._dialect) is False:
            return None
        message = StreamedMessage(self._on_chunk, self._on_thinking)
        try:
            stream_options = {}
            if self._feedback is not None:
                stream_options["feedback"] = self._feedback
            data = post_stream(
                self._endpoint,
                self._headers,
                {**body, "stream": True},
                message,
                self._timeout,
                self._verify,
                **stream_options,
            )
        except ApiResponseError as err:
            if thinking_unsupported(err) or not streaming_unsupported(err):
                raise
            set_supports_streaming(self._url, False, self._model, self._dialect)
            return None
        if not data.get("content"):
            set_supports_streaming(self._url, False, self._model, self._dialect)
            return None
        if get_supports_streaming(self._url, self._model, self._dialect) is None:
            set_supports_streaming(self._url, True, self._model, self._dialect)
        return data


def _as_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def consume_anthropic(
    chunks: list[bytes],
    on_text: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    accumulator = SseAccumulator()
    message = StreamedMessage(on_text, on_thinking)
    for chunk in chunks:
        for event in accumulator.feed(chunk):
            message.take(event)
    return message.response()
