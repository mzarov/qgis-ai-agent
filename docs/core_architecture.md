# Core Architecture

The architecture of `qgis_ai_agent`: an agent loop with skills.

## Goals

- keep `plugin.py` thin: bootstrap and QGIS wiring only
- let the agent **look** at the project before changing it
- keep the prompt from growing with the number of domains
- add a new domain with files, not by editing orchestration

## Package Layout

- `core/agent/` — the agent loop: run state, request assembly, tool execution, transcript
- `core/orchestrator/` — wires the UI to the loop and renders the run into the chat
- `core/llm/` — HTTP client, transport adapter, parser
- `core/context/` — the short starting summary of the project
- `core/state/` — the model's history window and the saved conversations
- `qgis_tools/common/` — shared across domains: layers, CRS, values, renderer summary
- `qgis_tools/` — tools by domain: `inspect/`, `style/`, `processing/`
- `skills/` — knowledge packages `<skill>/SKILL.md` and the registry

## Runtime Flow

1. `plugin.py` (the composition root above the layers) builds `AgentDockWidget`
   and `CoreOrchestrator`.
2. The orchestrator hands the user's request to `AgentLoop.start()`.
3. The loop assembles the request (`request.py`) and sends the turn to
   `ModelTurnThread`.
4. The reply arrives as a signal on the main thread — tools execute right there.
5. The loop repeats while the model keeps calling tools.
6. When the model replies without calls, the collected changes go to the user
   for confirmation.

## Threading model

PyQGIS and Qt objects may be touched only from the main thread. So the loop is
not a background `while` but a **state machine on the main thread**: only the
HTTP request leaves it, and `_on_turn` runs as a main-thread slot.

## Safety classes

Every tool declares `safety`:

| Class         | Behaviour                                              |
| ------------- | ------------------------------------------------------ |
| `read`        | runs immediately, no confirmation asked                |
| `write`       | collected into a batch, applied after the user's button |
| `destructive` | reserved for per-call confirmation                     |

A write call returns `{"status": "queued"}` to the model — a normal success
response, not an error. Changes apply only after the button is pressed.

## Validation before the queue

A write executes **after** the loop has ended, so at that point there is nobody
left to return an error to. Everything that can be checked and normalised from
the arguments is done by `BaseTool.prepare` at queue time — the loop is still
alive there, and the agent can rebuild the plan. The hook returns the corrected
arguments, and exactly those go into the queue: the user confirms precisely what
will run.

That is how, for example, the CRS unit check works: a metre buffer requested on
an `EPSG:4326` layer is rejected with a ready-made `native:reprojectlayer` call
in the error text, and the agent adds the reprojection step itself.

## Skills and progressive disclosure

A skill is a domain package: a `SKILL.md` with frontmatter (`name`,
`description`, `tools`) plus a body of rules. The system prompt permanently
holds only the one-liners of all skills. The body and the tool schemas load when
the agent calls the `load_skill` meta-tool. The `inspect` skill is always loaded
— otherwise a simple question would cost an extra turn.

Prompt growth as skills load (empty → inspect → +style → +processing):
2221 → 6942 → 9326 → 12012 characters. Without disclosure every request would
cost the maximum.

## Alignment with current practice (checked August 2026)

The format and the loading model deliberately match **Agent Skills** — the open
standard (agentskills.io) adopted across the ecosystem: required `name` and
`description` frontmatter, a Markdown body of instructions, and three-stage
progressive disclosure (metadata at startup → body on activation → resources on
demand). Our skill names satisfy the spec's naming rules and the bodies stay
well under its recommended 500-line cap. The one extension is our `tools` list
in the frontmatter, which binds a skill to its tool classes — the spec permits
extra fields via `metadata`, and we parse our own frontmatter anyway.

Two adjacent 2026 developments were evaluated and consciously not adopted:

- **MCP.** The Model Context Protocol standardises giving *external* agents
  access to live systems. Our plugin is the opposite shape: the agent lives
  inside QGIS and talks to a model over plain REST. Exposing QGIS tools as an
  MCP server would be a different product (QGIS for Claude Desktop and the
  like), a possible future skill-set consumer but not a replacement for the
  in-plugin loop — which vendor neutrality and the main-thread rule both
  require.
- **Skills served over MCP.** Useful when one organisation feeds many agents
  from a central skill registry. We have one agent and five skills shipped in
  the same zip; a transport layer between them would add a dependency and
  remove nothing.

## The Python escape hatch

`run_python` executes a PyQGIS snippet inside the running QGIS. It is a
permanent part of the design, not a temporary crutch: the agent is meant to
reach the whole QGIS API, and no realistic number of tools covers a thousand
classes. Everything below is a deliberate choice, so do not "optimise" it away.

**Why it is `destructive` rather than analysed.** Telling a reading snippet
from a writing one by static analysis is not possible — `getattr` chains defeat
it, and an AST allowlist would only produce a false sense of safety. So the
plugin does not pretend to judge the code. Instead the code itself is the
confirmation: the snippet is shown to the user in the destructive dialog before
anything runs, and the `intent` field — one plain sentence for a human — is
mandatory.

**Why the bandit finding is suppressed at the line, not in the config.**
`B102: exec_used` is a correct finding, not a false positive. Adding it to
`.bandit` skips would disable the check across the whole package and hide the
riskiest property of the code from a reviewer. A `#nosec B102` sits on the exec
line where the risk is, and `tests/test_publish_ready.py` keeps it honest:
`exec` appears in exactly one file, there is exactly one suppression, and the
tool using it must be destructive-class.

**Why a shell is not offered.** Everything QGIS can do is reachable from
Python. A system shell would widen the attack surface without widening what
the agent can accomplish in GIS terms.

Two guards sit under the confirmation: a line budget via `sys.settrace` stops a
runaway loop from freezing QGIS, and the snippet is compiled at queue time so a
syntax error is rejected while the loop is still alive to fix it.

`skills/python/SKILL.md` tells the agent to try a real tool first and to name
any successful snippet as a missing tool — the escape hatch doubles as a
signal for what to cover next.

## Transport

The plugin is not tied to a vendor: it talks to whatever address the user set in
the settings. The URL setting itself plays the “AI hub” role — no separate layer
is needed. It is enough that the endpoint understands the OpenAI Chat
Completions format, which nearly every corporate gateway does. The user provides
the URL, the key (kept in the keyring, not in config) and the model name.

`core/llm/transport.py` tries native function calling (`tools` +
`tool_choice`). If the endpoint answers with an error about the unsupported
parameter, the adapter switches to the JSON-in-prompt protocol and remembers the
choice in `QgsSettings` under a hash of the URL. Both paths normalise into one
`ModelTurn` — the loop does not know which one worked.

If an endpoint with a fundamentally different format appears, it gets its own
adapter next to `transport.py`, not edits to the loop.

### Streaming

The answer arrives word by word instead of appearing whole after a long pause.
This is the one place where `QgsBlockingNetworkRequest` cannot be used — it
hands back a finished reply and there is no way to read the body as it comes.
So the streaming path alone goes through `QgsNetworkAccessManager` with a
nested `QEventLoop`: from the caller's point of view the call still blocks, so
it stays inside the same background thread and the loop above it is unchanged.
The proxy and authentication settings of QGIS are honoured either way — both
classes sit on the same network stack.

The parsing splits in two on purpose. `llm/stream.py` is pure Python: it
reassembles Server-Sent Events across chunk boundaries and folds the deltas
into the ordinary completion shape, so `_parse_native_turn` handles a streamed
answer and a normal one identically. `llm/stream_runner.py` holds everything
Qt- and network-shaped. Only the first half needs tests, and it gets them.

Streaming follows the same feature-detect rule as `tools` and images: it is
attempted, and an endpoint that refuses is written down as `supports_streaming
= false` under the hash of its URL and never asked again. A failed attempt
falls through to the ordinary request, so a server without SSE loses the live
text and nothing else.

Text is forwarded to the UI only until the first tool-call delta. What the
model says before calling a tool is a preamble, not an answer: it is kept in
the transcript for the model, while the chat drops the draft when the tool
starts. Otherwise the chat would show text that the saved conversation does
not contain, and the next run would see something other than what the user
read.

## Adding a new domain

1. `qgis_tools/<domain>/` — tool classes with `skill = "<domain>"` and `safety`
2. `skills/<domain>/SKILL.md` — frontmatter and the domain rules
3. hook the tool list into `qgis_tools/registry.py`

Orchestration, the loop and the prompt stay untouched. Domains do not depend on
each other: shared code comes from `qgis_tools/common/`, so a domain can be
removed without breaking its neighbours.

## Conversations

A conversation outlives the QGIS session. `ConversationState` holds two things
at once:

- `HistoryStore` — the short window (`WINDOW_LIMIT` messages) that goes to the model
- `Session` — the full transcript, the one that reaches the disk

One message is added with one `add(role, text)` call — the two stores must never
diverge. Saving happens right after every message, so a QGIS crash does not eat
the conversation.

`SessionStore` writes one JSON per conversation into `qgis_ai_agent_sessions/`
inside the QGIS profile. A conversation is bound to its project: `recent()`
returns only those started in the currently open project, and an unsaved project
gets the shared “no project” bucket. The title comes from the user's first
message.

An empty conversation is never written to disk, otherwise the list would fill
with traces of accidental clicks. Old conversations are trimmed to
`MAX_SESSIONS`, and only when a new file appears — rewriting an existing one
must not walk the whole folder.

What is saved is the conversation, not the run: tool calls and plan cards do not
come back on restore. The outcome of applying does get recorded as an agent
message — otherwise the model would not know on its next turn whether its
changes landed (`confirm_pending` ends the run and does not return the result to
the loop).

Switching conversations is forbidden while the loop is running or waiting for a
write confirmation: otherwise the collected batch would apply to a conversation
that never asked for it.

## History

Print layouts were a separate domain until `0.2.0` and were removed: they are to
be rebuilt. The working implementation is preserved in the `v0.1.0-diploma` tag.

## Prompt Policy

- system prompts and `SKILL.md` are written in English, like everything else
- the reply language is set not by the prompt text but by
  `language_policy(locale)`: the QGIS interface language goes into the prompt,
  and the model is told to switch to the user's language when they write in a
  different one
- interface text is an English original inside `tr()` plus a `.qm` next to it
