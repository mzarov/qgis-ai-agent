# Core architecture

How the agent inside `ai_agent` works and why it is built this way.

## Package layout

- `plugin.py` is the composition root: it builds the dock widget and the
  orchestrator and wires them to QGIS.
- `core/agent/` holds the loop: run state, request assembly, tool execution,
  the transcript, Apply and the check after it.
- `core/orchestrator/` connects the UI to the loop and renders a run into the
  chat.
- `core/llm/` is the HTTP client, the two API dialects and the parsers.
- `core/state/` keeps the model's window and the saved conversations.
- `qgis_tools/<domain>/` holds the tools, one class per file;
  `qgis_tools/common/` holds code shared across domains.
- `skills/<domain>/SKILL.md` holds the rules of each domain.

## No agent framework

The loop is our own code. Agent frameworks do not fit a QGIS plugin:

- Each one is a dependency, and the plugin runs in the QGIS Python, where every
  extra package is an installation problem for the user. Today the plugin has
  none.
- Most are built around one vendor's SDK. The plugin must work with any
  OpenAI-compatible endpoint and with local servers.
- They run the loop on a background thread or with `asyncio`. PyQGIS objects
  may be touched only from the main thread, so such a loop crashes QGIS.
- The loop itself is small. What it needs beyond a framework is QGIS-specific:
  a batch the user applies, a project snapshot, a check after Apply.

The same reasons rule out exposing the tools over MCP instead: the agent lives
inside QGIS and talks to a model over plain REST.

## The loop

The loop works act, observe, decide. It is not a one-shot planner.

1. The orchestrator hands the request to `AgentLoop.start()`.
2. The loop assembles the request (`request.py`) and sends it from
   `ModelTurnThread`.
3. The reply arrives on the main thread as a signal. Local reads run at once
   and their results go back to the model. Writes and network reads join a
   batch.
4. The loop repeats while the model calls tools.
5. A run ends when the model replies without tool calls. The batch then goes
   to the user.

A step limit and a token budget from the settings stop a runaway run with a
plain explanation.

## Safety classes

Every tool declares `safety`:

- `read` runs at once, unless it declares `network_access`.
- `write` joins a batch that runs after the user presses Apply.
- `destructive` also joins the batch and asks for a separate confirmation of
  each call.

A write call returns `{"status": "queued"}` to the model. That is success, not
an error.

A read with `network_access = True` is queued too, and the run pauses for the
user to approve that exact call. Its result then enters the transcript and the
run resumes. A batch of network reads only does not take a project snapshot,
because it changes nothing in QGIS.

**Auto mode** presses Apply for the user (`agent/auto_apply.py`). A batch
applies itself only when no call in it is destructive or unknown, and never
after a failed run. It then takes the same path as the button: snapshot,
destructive check, verification.

**Plan mode** offers read tools only. The dispatcher refuses any other call.
The run ends with a numbered plan and an offer to carry it out in Ask or Auto
mode.

### Validation before the queue

A write runs after the loop has ended, when nobody is left to read an error.
So `BaseTool.prepare` checks and normalises the arguments when the call is
queued, while the model can still fix them. The corrected arguments go into
the queue, so the user confirms exactly what will run. For example, a buffer
in metres on a layer in degrees is refused with a ready `native:reprojectlayer`
call in the error, and the model adds that step itself.

### Snapshots and the check after Apply

Every applied batch with a write takes a project snapshot first. Undo on the
plan card and rewinding to an earlier message restore these snapshots
(`orchestrator/rewind.py`).

QGIS 4 writes every `.qgz` through one fixed file in the system temp folder,
`qgis-project-XXXXXX.zip`, then renames it into place. Two QGIS processes
saving at the same moment share that file: one save fails, or one project file
ends up holding the other process's project. A snapshot therefore checks that
the archive it wrote holds its own project file and writes it again if not
(`project/snapshots.py`). The real-QGIS tests give every QGIS process its own
temp folder, so parallel runs never meet in that file.

After Apply the orchestrator checks the result. First it reads: each write
tool may answer `confirm_applied` with the one read that proves its step.
When every step of a successful batch reads back as done, no model run starts.
Otherwise a verification run starts: the model re-reads the result, looks at a
rendered image for visual changes and queues fixes for what the request asked
for and did not get. A tool that cannot be sure returns `None` from
`confirm_applied`; a false "done" is the one failure this check must not have.

## Main thread and background tasks

PyQGIS and Qt objects may be touched only from the main thread. So the loop is
a state machine on the main thread. The HTTP request runs in `ModelTurnThread`;
`_on_turn` and tool execution run as main-thread slots.

A long step would freeze QGIS for as long as it runs. So a tool may hand its
heavy part to a QGIS task (`BaseTool.start`, `qgis_tools/common/background.py`):

- a Processing algorithm through `QgsProcessingAlgRunnerTask`, as the
  Processing toolbox does for "Run in background";
- a download through `qgis_tools/common/network.py`, which waits in the task's
  own thread.

The task touches only thread-safe objects. The project, layers and widgets are
touched when it ends, back on the main thread. The apply run
(`agent/apply_run.py`) returns to the Qt event loop while the task works and
continues on its signal; Stop cancels the task and the steps after it.
Algorithms flagged NoThreading still run on the main thread.

Never move a whole tool or the loop to a background thread, and never rewrite
the loop as a background `while` or with `asyncio`.

### Network calls off the main thread

PyQt and the GIL set traps for a worker thread that talks HTTP, and
`qgis_tools/common/network.py::send` is the one place that knows them:

- A `QgsBlockingNetworkRequest` made from Python can freeze QGIS for good when
  it runs off the main thread. When it finishes, QGIS destroys its private
  event loop while holding a Qt lock and asks Python whether the request
  object, the feedback passed with it or a Python-made application object
  overrides `disconnectNotify`; the question needs the GIL. A main thread that holds the GIL and waits for the
  same lock (any `connect`, such as a style sheet on a new widget) never gets
  it. sip remembers a "no" per object, so `send` asks once itself, with the GIL
  held and no Qt lock taken, before the request starts; the request itself
  then runs without the GIL. Running the request on `QgsNetworkAccessManager`
  from Python instead only turns the deadlock around: the worker then holds
  the GIL while Qt takes its locks, and a main thread deleting an object
  connected to a Python-made widget takes a lock first and the GIL second.
- A stream needs the body as it arrives, so `send` runs it on
  `QgsNetworkAccessManager` in the thread's own event loop, which keeps that
  rarer reversed risk; every Python worker that emits signals has it too.
- PyQt 6 reports the deletion of a QObject made in C++ to the main thread, by
  address. A report about a reply or network manager deleted in a worker can
  arrive after the address was reused, and then marks a newer, live object as
  deleted: the next model turn failed before its request was even sent. `send`
  cuts that report on the manager and the reply of a stream.

## Skills and progressive disclosure

A skill is a domain package: `SKILL.md` with frontmatter (`name`,
`description`, `tools`) and a body of rules. The system prompt always holds one
line per skill. The body and the tool schemas load when the model calls
`load_skill`. `inspect` is always loaded, so a simple question costs no extra
turn. Without this, every request would carry every schema, and the prompt
would grow with each new domain.

The format follows the open Agent Skills standard (agentskills.io): `name` and
`description` frontmatter, a Markdown body, loading on demand. The `tools` list
is our extension; it binds a skill to its tool classes.

Domain rules live only in `SKILL.md`. `core/agent/prompts.py` holds
domain-independent behaviour only.

## The Python escape hatch

`run_python` runs a PyQGIS snippet inside QGIS. It is a permanent part of the
design. The agent should reach the whole QGIS API, and no number of tools
covers thousands of classes.

- It is `destructive` rather than analysed. Static analysis cannot tell a
  reading snippet from a writing one, so the plugin does not pretend to. The
  user sees the code in the confirmation dialog before anything runs, with a
  required one-sentence `intent`.
- The bandit finding `B102: exec_used` is real. It is suppressed with
  `#nosec B102` on the one `exec` line, not in a config file, so the check
  stays on for the rest of the package. `tests/test_publish_ready.py` keeps
  `exec` in one file, with one suppression, in a destructive tool.
- There is no shell tool. Everything QGIS can do is reachable from Python; a
  shell would only widen the attack surface.
- A line budget (`sys.settrace`) stops a runaway loop, and the snippet is
  compiled when queued, so a syntax error comes back while the loop can fix it.

`skills/python/SKILL.md` tells the model to try a real tool first. A snippet
that works points at a missing tool.

## Transport

The plugin talks to whatever address the user sets. The endpoint needs to
speak OpenAI Chat Completions or the Anthropic Messages API; there are no
provider SDKs.

`core/llm/transport.py` tries native function calling first. If the endpoint
rejects the `tools` parameter, it switches to a JSON-in-prompt protocol and
remembers that for the endpoint. Both paths produce the same `ModelTurn`.
Streaming, images and reasoning follow the same rule: try, and remember a
refusal per endpoint. A refusal is told apart from an outage, so a 401 or 429
never switches a feature off.

All HTTP stays on the QGIS network stack, so QGIS proxy and authentication
settings apply. Ordinary calls use `QgsBlockingNetworkRequest` and streaming
uses `QgsNetworkAccessManager` with a nested event loop, both through
`qgis_tools/common/network.py` (see "Network calls off the main thread").
The web tools run their own `QgsNetworkAccessManager` loop on the main
thread, because they need the body while it arrives. They also accept only
public DNS answers, pin a checked IP while TLS verifies the original host name, follow
only same-origin redirects they have checked, pass the host name to an
explicit QGIS proxy and fail closed when a direct route does not match.

### Reasoning

Reasoning arrives in three shapes, and all are handled:

- Local servers put it in `content` inside `<think>` tags. `llm/thinking.py`
  cuts it out, also when a tag is split across chunks.
- DeepSeek and OpenRouter send a separate `reasoning_content` field.
- Anthropic returns signed `thinking` blocks. With tools in the same run the
  API requires them back, so `ModelTurn` carries them and they are re-sent
  first in the assistant message.

Otherwise reasoning is shown in the chat and never sent back, with one
exception: DeepSeek in thinking mode answers 400 unless every earlier
assistant message carries its `reasoning_content`, so with the Reasoning
switch on it is echoed there. The saved conversation keeps reasoning for the
chat only.

Some models reason only when asked, and there is no standard way to ask. The
**Reasoning** switch (off by default) becomes the parameter the host expects
(`llm/reasoning.py`): `thinking` for DeepSeek, `reasoning.effort` for
OpenRouter and `reasoning_effort` for every other host. An unknown host gets
`reasoning_effort` because most compatible servers copied it; a server that
rejects it costs one retry, and the refusal is remembered as
`supports_thinking = false`. This check runs before the streaming and tools
checks, so a complaint about `reasoning_effort` never turns streaming off.

## Conversations

`ConversationState` wraps one `Session`: the full transcript plus the summary
left by the last compaction. The model's window is the summary and every
message after it. The conversation is saved after every message as JSON in
`ai_agent_sessions/` in the QGIS profile, bound to the open project. The chat
also saves what it showed of each turn (steps, reasoning, plan cards); none of
that reaches the model. Switching conversations is refused while a run or an
unapplied batch is active.

## Prompt policy

- System prompts, `SKILL.md` and tool schemas are English.
- The reply language comes from `language_policy(locale)`: the QGIS interface
  language goes into the prompt, and the model switches to the user's language
  when they write in another one.
- Interface text is an English original inside `tr()` plus a compiled `.qm`.
