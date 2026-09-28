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
              ├─ local safety=read   → execute now, result into the transcript
              ├─ write/network read  → prepare, then into the confirmation batch
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
   Streaming and web redirects are the two exceptions to
   `QgsBlockingNetworkRequest`; both use `QgsNetworkAccessManager` with a nested
   `QEventLoop`. Streaming needs a body as it arrives. The web runner resolves
   with Qt, requires every DNS answer to be public, tries pinned addresses while
   TLS verifies the approved host, and follows only manually checked same-origin
   redirects. Explicit QGIS proxies receive the hostname; direct-route mismatches
   are blocked. Streaming remains
   blocking for the caller and on the background thread. Parsing lives apart in
   `llm/stream.py`, pure Python and therefore testable. A refusing endpoint is
   remembered as `supports_streaming = false` and falls back to one request —
   but only a genuine refusal counts. `llm/refusals.py` requires the feature
   named next to a refusal phrase, or a structured error pointing at the
   feature's parameter; a context overflow, a quota error or a thinking
   signature error never counts, and bare fragments like "stream" or
   "function" are not enough. A 401 or a 429 says nothing about streaming and
   is raised as itself. A stream that yields no SSE events at all is a refusal
   — a server ignoring `stream`; its plain JSON body is read as the answer. An
   error event inside a 200 stream is raised as an API error (overloaded →
   529), and a stream that closes without `[DONE]` / a finish reason /
   `message_stop` is incomplete, never a short answer. A successful connection
   test in Settings forgets everything detected about that endpoint.
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
   with a plain explanation — never by silently stopping. A failed run
   (`_fail`) keeps its prepared batch and offers it after the error: a transport
   error at turn thirty must not throw away validated work. Only Stop clears it.
   A run that ends — completed or failed — is never left staged.
   A final reply cut off by the output limit, or an empty one, gets exactly one
   more turn with a plugin note (`notices.CONTINUE_TRUNCATED` / `EMPTY_REPLY`);
   the cut-off text is kept as a preamble first so the chat does not lose it.
   The queued steps the model sees are `WriteBatch.pending_lines()` — tool name
   and public arguments, never the translated UI summaries — and an identical
   second call is answered `duplicate: true` instead of a silent success.
8. **A run can pause and resume.** `apply_now` marks the run staged: the loop
   emits `confirm_needed` but does **not** end. On confirm, the batch executes,
   its real results go into the same transcript and `_request_step` continues;
   on cancel the run ends with a stated reason. The invariant is unchanged —
   writes still only run after the user's button. What changed is that the run
   no longer dies at the first batch, which is what lets one request finish a
   multi-stage task.
   A read with `network_access = True` auto-stages the run for exact per-call
   confirmation. A batch containing only network reads skips the project
   snapshot because it cannot mutate QGIS.
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
   out in the background; the result is discarded by the `_aborted` flag.
   Plugin unload cancels and waits for every thread, retired ones included, and
   keeps a thread that is still running alive until it finishes; nothing ever
   calls `terminate`.
15. **Keys live in the QGIS authentication database.** `credentials.py` talks to
    `QgsAuthManager`: the encrypted `qgis-auth.db` inside the profile, the same
    store QGIS uses for layer passwords. The earlier `keyring` route was the
    plugin's only external dependency and it does not ship with QGIS — every
    user had to pip-install it into the QGIS Python before the plugin worked at
    all, which is not an install story. `QgsAuthManager` needs nothing, behaves
    the same on all three platforms, and the master password is a dialog the
    user already knows. Only the identifier of the stored entry goes into
    `QgsSettings`; the secret never does. A refused master password reads as an
    empty key with a stated reason, never as a crash.
16. **Slash commands preload skills; the loop stays skill-agnostic.**
    `orchestrator/slash.py` parses `/name rest`: an unknown name is refused with
    the list before anything is sent; a known one becomes
    `AgentLoop.start(prompt, history, skills=[name])`. The loop extends its
    preloaded skills through `agent/skills.extend_loaded` (a local skill drags
    in the domains of its tools) and names them under `INVOKED_SKILLS_HEADER`
    so the model treats their rules as the user's explicit choice. The chat and
    the saved conversation keep the original `/name …` text; the model gets the
    request without the command. `core/local_skills.py` owns the profile
    directory, the rescan and the example file — the `skills/` layer never
    touches `qgis`.
17. **The transport retries, but only what is worth retrying.** `llm/retry.py`
    wraps every `_dispatch` in `call_model`: three attempts, backoff 1.5 s then
    4 s or the server's `Retry-After` (capped at 30 s), on 408/425/429 and every
    status ≥ 500 (529 is Anthropic's overload), never on a 429 for an exhausted
    quota, and on connection failures that came back **fast**
    (under `FAST_FAILURE_SECONDS`) — a fast failure is a reset or a refusal, a
    slow one is a timeout that would only time out again. Never after a stream
    has delivered chunks (the draft would be duplicated), never after the user
    cancelled (the pause polls the feedback every quarter second); streamed
    reasoning counts as delivered too. Retries are logged to the QGIS message
    log, not shown in the feed. Blocking calls wait `blocking_timeout` — five
    times the stream idle limit — because a non-streamed answer arrives only
    when the model is done.
18. **The prefix never moves; the state rides at the end.** Everything that
    changes during a run — notes, plan, queued steps, project context — is one
    state message appended after the transcript (`llm/live.py`), never part of
    the system prompt. The system prompt, the tool list and every earlier message
    stay byte-identical from turn to turn, so a prefix-caching provider
    (Anthropic breakpoints, OpenAI, DeepSeek) bills only the new turn. Anthropic
    gets the state as a trailing text block after the message breakpoint;
    other dialects get it folded into the last message by `fold_live`, because
    several chat templates reject two user turns in a row or a user turn right
    after a tool result. Transcript compaction moves in steps of `COMPACT_STEP`
    for the same reason, and the verification run starts with the applying
    run's skills so its tools and system prompt match the prefix just cached.
    New per-turn text goes into the state message, never into the system prompt.
19. **The project context is a real briefing, kept to metadata.** Project CRS,
    the active layer, and per layer geometry, CRS, selection count and — only
    for local providers in `COUNTABLE_PROVIDERS` — the feature count. Remote
    providers are never asked to count: `COUNT(*)` on a big table would stall
    the main thread before the first turn. Extents and values stay behind the
    sensitive-data switch.
20. **Anthropic thinking follows the model generation.** `anthropic.thinking_config`:
    Fable, Mythos and Opus 5.5 always think (no `disabled`, no `budget_tokens`);
    the 4.6+ generation takes only `adaptive`; older models keep
    `budget_tokens`. `display: "summarized"` where the default is "omitted".
    Thinking blocks go back unchanged whenever the model may have produced
    them. Models that bind a thinking block to the exact conversation prefix
    (Fable 5.1, Mythos 5.1, Opus 5.5) get `block_binding: drop_block` with the
    `thinking-binding-controls` beta on api.anthropic.com: the state message
    and compaction edit history every turn, so a mismatched block is dropped
    instead of failing the request. A turn cut off by `max_tokens` with tool
    calls runs none of them and tells the model to resend.
21. **Imports** — all at the top, absolute. Use concise contract docstrings and
    comments for non-obvious reasons — see the root CLAUDE.md.

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
| `llm/retry.py`           | bounded retries around a model call, cancellation-aware |
| `llm/live.py`            | the per-turn state message and how each dialect receives it |
| `llm/images.py`          | finding and stripping image blocks in messages       |
| `llm/thinking.py`        | cutting `<think>` out of content, across chunks      |
| `llm/dialects.py`        | dialect detection from the address, paths, headers  |
| `llm/anthropic.py`       | messages and tool schemas in the Anthropic format   |
| `llm/client.py`          | the HTTP layer, URL/key/header resolution           |
| `llm/probe.py`           | the connection check for the settings dialog        |
| `llm/providers.py`       | provider presets for the settings dialog            |
| `credentials.py`         | API keys in the QGIS authentication database        |
| `local_skills.py`        | the profile's skills folder: rescan, validation, example |
| `orchestrator/slash.py`  | `/skill` parsing and the skill list for the composer |
| `orchestrator/`          | UI-to-loop wiring, the DockWidget contract          |
| `state/conversation.py`  | the model window and the current dialogue, one entry point |
| `state/session.py`       | the conversation model: title, messages, serialising |
| `state/store.py`         | conversations on disk, filtered by the open project |
