# core/ — the agent's brain

The agent loop, orchestration, LLM transport and state live here.
PyQGIS execution logic does not move in — it belongs to `qgis_tools/`.

## Control flow

```
UI signal → CoreOrchestrator → AgentLoop.start()
              ↓
        request.py assembles messages + tool schemas
              ↓
        ModelTurnThread (background thread, HTTP only)
              ↓  signal
        AgentLoop._on_turn (MAIN thread)
              ├─ no calls            → final answer, run over
              ├─ safety=read         → execute now, result into the transcript
              ├─ safety=write        → prepare, then into the batch, return "queued"
              └─ load_skill          → load the domain, return its tool list
              ↓
        _request_step() — the next iteration
```

## Rules

1. **Main thread.** `_on_turn` and `ToolExecutor.run` must run on the main
   thread — they touch PyQGIS there. Only the HTTP call goes to the background.
   Do not rewrite the loop as a background `while` or as `asyncio`.
2. **Writes are validated before the queue.** `BaseTool.prepare` is called in
   `_queue_write` while the loop is alive. Execution itself happens after the
   loop ends, and there is nobody left to return an error to — so everything
   checkable from the arguments is checked here.
3. **A tool error does not kill the run.** `ToolExecutor` catches the exception
   and returns it to the model as a result, so the model corrects itself.
   Never propagate it out.
4. **`prompts.py` holds domain-independent behaviour only.** Any rule about a
   specific domain or specific tools goes to `skills/<domain>/SKILL.md`.
   The urge to add a rule to the system prompt is a signal that a skill is
   needed.
5. **Transport is vendor-neutral.** Two dialects: `openai`
   (`/chat/completions`, Bearer) and `anthropic` (`/messages`, `x-api-key`,
   system prompt outside the message list). Picked from the address, with a
   manual override in the settings. Inside the openai dialect the transport
   tries native `tool_calls`, falls back to the JSON protocol on refusal and
   remembers the choice in `QgsSettings` under a hash of the URL. All paths
   normalise into `ModelTurn` — the loop does not know which one worked.
   Never add provider SDKs: a dialect is a shape of HTTP, not a library.
   Streaming is the one exception to `QgsBlockingNetworkRequest`: it cannot
   read a body as it arrives, so `llm/stream_runner.py` uses
   `QgsNetworkAccessManager` with a nested `QEventLoop` — still blocking for
   the caller, still on the background thread. Parsing lives apart from it in
   `llm/stream.py`, pure Python and therefore testable. A refusing endpoint is
   remembered as `supports_streaming = false` and falls back to one request —
   but only a genuine refusal counts. A 401 or a 429 says nothing about
   streaming, and disabling the feature over one would be permanent and
   silent; those are raised as themselves. A stream that yields no events at
   all is a refusal too — that is a server ignoring `stream`, not an empty
   answer.
   Live deltas stop reaching the UI at the first tool-call delta, but the
   preamble is not lost: once the turn arrives, the loop emits it whole and the
   orchestrator saves it like any answer — so the chat keeps the text and still
   matches the saved conversation. The view-level draft drop remains only as a
   safety net for text that was never finalised.
   Both dialects stream, each with its own fold: openai has one delta shape,
   anthropic a typed event per step ending in `message_stop`, not `[DONE]`.
   `refusals.py` keeps the three refusals apart — mixing them up disables the
   wrong feature, so a thinking complaint must be raised, not swallowed as a
   streaming one.
6. **Reasoning is separated, never echoed back.** Three shapes arrive:
   `<think>` inside `content` (local servers), a `reasoning_content` field
   (DeepSeek, OpenRouter) and Anthropic `thinking` blocks. `llm/thinking.py`
   cuts the tags out — across chunk boundaries, and before the JSON protocol
   parses, or the parser may pick a candidate object out of the reasoning.
   The reasoning **text** goes to the UI only and never back to the model or
   into the saved conversation. Anthropic blocks are the exception: with tools
   in the run the API demands them back verbatim with their `signature`, so
   `ModelTurn` carries them, the transcript keeps them and `_assistant_message`
   re-emits them first.
7. **`MAX_ITERATIONS`** guards against endless loops, and a token budget from
   the settings guards the user's wallet. Both end the run through `_complete`
   with a plain explanation — never by silently stopping.
8. **A run can pause and resume.** `apply_now` marks the run staged: the loop
   emits `confirm_needed` but does **not** end. On confirm, the batch executes,
   its real results go into the same transcript and `_request_step` continues;
   on cancel the run ends with a stated reason. The invariant is unchanged —
   writes still only run after the user's button. What changed is that the run
   no longer dies at the first batch, which is what lets one request finish a
   multi-stage task.
9. **The run can also pause on a question.** `ask_user` is the second use of
   the same pause mechanic as `apply_now`: the loop emits `question_asked`,
   releases the thread, and the user's next message resumes the SAME run via
   `answer()` instead of starting a new one. The prompt forbids using it for
   plan approval — queueing is the proposal; a question is only for decisions
   that are genuinely the user's.
10. **The user can break in mid-run.** `interject` appends the message to the
   live transcript framed as a correction, so the model sees it on its next
   step instead of the run having to be restarted. The composer stays editable
   while busy for exactly this; the ■ button is still an abort, not a send.
11. **The transcript compacts itself.** Only the last `KEEP_FULL_RESULTS` tool
   results are rendered in full and only the newest image is carried; older ones
   become short notes. Without this a forty-turn run would not fit the model
   window. Compaction happens at render time — the entries themselves are never
   mutated, so the saved conversation stays complete.
12. **The orchestrator only renders.** Decisions belong to the loop;
   `CoreOrchestrator` subscribes to signals and draws them into the chat.
   Do not add branching logic there.
13. **A message is written with one call.** `ConversationState.add` puts it both
   into the model's window and into the saved session. Never call
   `HistoryStore` and `Session` separately — they diverge, and the model would
   see something other than what the chat shows.
14. **Aborting never blocks the main thread.** `abort` does not wait and does not
   kill the thread — it disconnects the signals and lets the HTTP request burn
   out in the background; the result is discarded by the `_aborted` flag. The
   hard `stop` with `terminate` remains only for plugin unload, when QGIS is
   closing anyway.
15. **Imports** — all at the top, absolute. Code without comments or docstrings
    — see the root CLAUDE.md.

## What lives where

| File                     | Responsibility                                      |
| ------------------------ | --------------------------------------------------- |
| `agent/loop.py`          | the run state machine                               |
| `agent/turn_thread.py`   | background-thread ownership: start, detach, stop    |
| `agent/notices.py`       | the texts the loop hands outwards                   |
| `agent/request.py`       | messages, tool schemas and transport settings       |
| `agent/executor.py`      | tool-call execution with error capture              |
| `agent/transcript.py`    | the run transcript and rendering for both protocols |
| `agent/prompts.py`       | the system prompt core, the `load_skill` meta-tool  |
| `llm/transport.py`       | dialect choice, feature detect, ModelTurn normalising |
| `llm/stream.py`          | SSE framing, openai delta folding, pure Python       |
| `llm/anthropic_stream.py`| anthropic event folding and its streaming exchange   |
| `llm/stream_runner.py`   | the streaming request itself: NAM, nested event loop |
| `llm/refusals.py`        | telling an unsupported feature from a broken request |
| `llm/images.py`          | finding and stripping image blocks in messages       |
| `llm/thinking.py`        | cutting `<think>` out of content, across chunks      |
| `llm/dialects.py`        | dialect detection from the address, paths, headers  |
| `llm/anthropic.py`       | messages and tool schemas in the Anthropic format   |
| `llm/client.py`          | the HTTP layer, URL/key/header resolution           |
| `llm/probe.py`           | the connection check for the settings dialog        |
| `llm/providers.py`       | provider presets for the settings dialog            |
| `orchestrator/`          | UI-to-loop wiring, the DockWidget contract          |
| `state/conversation.py`  | the model window and the current dialogue, one entry point |
| `state/session.py`       | the conversation model: title, messages, serialising |
| `state/store.py`         | conversations on disk, filtered by the open project |
