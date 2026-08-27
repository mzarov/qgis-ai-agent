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
6. **`MAX_ITERATIONS`** guards against endless loops. Do not remove or raise it
   without a reason.
7. **The orchestrator only renders.** Decisions belong to the loop;
   `CoreOrchestrator` subscribes to signals and draws them into the chat.
   Do not add branching logic there.
8. **A message is written with one call.** `ConversationState.add` puts it both
   into the model's window and into the saved session. Never call
   `HistoryStore` and `Session` separately — they diverge, and the model would
   see something other than what the chat shows.
9. **Aborting never blocks the main thread.** `abort` does not wait and does not
   kill the thread — it disconnects the signals and lets the HTTP request burn
   out in the background; the result is discarded by the `_aborted` flag. The
   hard `stop` with `terminate` remains only for plugin unload, when QGIS is
   closing anyway.
10. **Imports** — all at the top, absolute. Code without comments or docstrings
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
| `llm/dialects.py`        | dialect detection from the address, paths, headers  |
| `llm/anthropic.py`       | messages and tool schemas in the Anthropic format   |
| `llm/client.py`          | the HTTP layer, URL/key/header resolution           |
| `llm/probe.py`           | the connection check for the settings dialog        |
| `llm/providers.py`       | provider presets for the settings dialog            |
| `orchestrator/`          | UI-to-loop wiring, the DockWidget contract          |
| `state/conversation.py`  | the model window and the current dialogue, one entry point |
| `state/session.py`       | the conversation model: title, messages, serialising |
| `state/store.py`         | conversations on disk, filtered by the open project |
