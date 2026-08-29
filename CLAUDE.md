# AI Agent

A plugin for QGIS 4 LTR: an AI agent that inspects the project and processes data
from a plain-language request.

Domains are implemented as skills: `inspect` (reading the project, selection,
rendering the map to an image), `project` (layers, basemaps, web services,
PostGIS, tree, bookmarks, undo, saving), `style` (vector and raster styling,
labels), `processing` (algorithms), `osm` (OpenStreetMap data through
Overpass), `edit` (in-place attribute edits and deletion — the `destructive`
class), `fields` (attribute schema and virtual fields), `layout` (print
layouts and export), `python` (the `run_python` escape hatch to the whole
QGIS API, destructive so the user reads the code first — it is a permanent
part of the design, never propose cutting it for review reasons; the
reasoning is in [docs/core_architecture.md](docs/core_architecture.md)), and
`web` (confirmed public-HTTPS search, page reading and geocoding),
`annotations` (map notes and markers), and `three_d` (opening a 3D map view).
After
the user applies a batch, the orchestrator starts a verification run: the agent
re-reads the result with read tools and, for visual changes, looks at a
rendered image.

Architecture and prompt design belong to the user; implementation belongs to the
agent. Do not ask permission for routine decisions — write the code.

## Stack

- QGIS 4 LTR, Python 3 with strict type hints
- GUI: **only** through the QGIS wrapper (`from qgis.PyQt.QtWidgets import QWidget`).
  Never directly from `PyQt5`, `PyQt6`, `PySide2`, `PySide6`. No Qt Designer and no
  `.ui` files — the interface is built in code.
- LLM: any OpenAI-compatible REST API. Vendor neutrality is a principle, not a
  detail: no SDK tied to a single provider.
- Secrets: `keyring` only (the system keychain). Keys are never written to config.
  An address on `localhost` needs no key — otherwise vendor neutrality would be
  words only: local servers (Ollama, LM Studio) require no keys.
- Dependencies: Poetry, Python `^3.12`. The plugin runs inside QGIS, so every new
  dependency is an installation problem for the user. Add one only when strictly
  necessary; today there is exactly one — `keyring`. **All HTTP stays on the
  QGIS network stack**, never `requests`: ordinary calls use
  `QgsBlockingNetworkRequest`; streaming and web redirects use
  `QgsNetworkAccessManager` with a nested event loop. Web requests validate all
  DNS answers, pin one public IP while verifying the original TLS host, and
  follow only manually checked same-origin redirects. A QGIS proxy-route
  mismatch fails closed.

## Architecture

Details: [docs/core_architecture.md](docs/core_architecture.md).

1. **No backend.** All logic lives inside the plugin. No agent framework — the
   loop is our own (the reasoning is in that document).
2. **Agent loop.** UI emits signals → `CoreOrchestrator` → `AgentLoop`. The loop
   works act → observe → decide: the model calls tools, sees results, picks the
   next step. It is **not** a one-shot planner. A run ends when the model replies
   without tool calls.
3. **Safety classes instead of “plan → confirm”.** Every tool declares `safety`:
   - `read` — executes immediately unless it declares `network_access`
   - `write` — collected into a batch, applied after the user presses the button
   - `destructive` — reserved for per-call confirmation

   A write call returns `{"status": "queued"}` to the model — that is success,
   not an error.
   A network read also queues, pauses automatically for exact per-call consent,
   and skips the project snapshot when the batch contains no mutation.
4. **A tool and a skill are different things — do not mix the words:**
   - **tool** — one `BaseTool` subclass in `qgis_tools/<domain>/`, one class per file
   - **skill** — a domain package `skills/<domain>/SKILL.md`: frontmatter (`name`,
     `description`, `tools`) plus a body with the domain rules
5. **Progressive disclosure.** The system prompt permanently holds only one line
   per skill. The `SKILL.md` body and the tool schemas load when the model calls
   `load_skill`. **Never add a domain rule to `core/agent/prompts.py`** — only
   domain-independent behaviour lives there.
6. **A new domain is added with files, not by editing orchestration:**
   `qgis_tools/<domain>/` + `skills/<domain>/SKILL.md` + one line in
   `qgis_tools/registry.py`.

## Main thread — critical

PyQGIS and Qt objects may be touched **only from the main thread**. That is why
the agent loop is a state machine on the main thread: the single outgoing HTTP
request runs in `ModelTurnThread`, while `_on_turn` and tool execution run as a
main-thread slot.

Never move tool execution to a background thread and never rewrite the loop as a
background `while` or as `asyncio` — that crashes QGIS.

## PyQGIS — do not hallucinate

- The QGIS 4 API is entirely different from QGIS 2. `QgsComposition` does not exist.
- Project state — always through `QgsProject.instance()`.
- Processing: `QgsApplication.processingRegistry()`, the `processing` module.
- Layouts: `QgsLayout`, `QgsProject.instance().layoutManager()` — needed when the
  layout domain returns.
- Unsure about a PyQGIS method? Find it in the “PyQGIS Developer Cookbook 3.40”
  first, then write the code.

## Language

- **The repository speaks English — all of it.** Code, identifiers, tool schemas,
  system prompts, `SKILL.md`, error messages, UI text, README, docs, CLAUDE.md
  files. Russian exists in exactly two sanctioned places: the translation
  catalogue in `ai_agent/translations/` and the human docs mirror —
  every `docs/*.md` has a `docs/*.ru.md` twin for the Russian half of the docs
  site. `tests/test_i18n.py` enforces the source side.
- **Documentation has two readers and two layers.** `CLAUDE.md` files are the
  agent layer: rules and invariants, always in context, kept terse, English
  only. `docs/` is the human layer: the MkDocs site, bilingual. Long rationale
  belongs in `docs/` with a link from the rule — never duplicated in both.
  When editing a `docs/*.md`, mirror the change in its `*.ru.md` twin.
- **User-facing text is wrapped in `tr()`, model-facing text is not.** There are
  two readers and they differ: `summarize_call` and `ui/` are read by a person,
  so `tr("Apply")`; tool `description`s, schemas and errors are read by the
  model, so plain English. Piping prompt text through `tr()` would send the
  model Russian schemas — noticeably worse than English ones.
- `tr()` takes a string literal only: `tr("Layer '{0}'").format(name)`, never an
  f-string. `update_translations.py` cannot extract anything from an f-string.

## Code style

- **No comments and no docstrings.** None at all: no `#`, no `"""..."""`.
  Clarity comes from names and function size. If something is unreadable without
  an explanation, that is a signal to rename or split, not to write a comment.
- Magic values become named module constants — they replace explanations
  (`SUSPICIOUS_DEGREES`, `MAX_ITERATIONS`, `PENDING_MARKER`).
- PEP 8, type hints everywhere
  (`def execute(self, params: dict[str, Any]) -> dict[str, Any]:`).
- Formatting and import order are owned by **ruff** (`ruff format` +
  `ruff check --fix`), wired as a pre-commit hook. Do not hand-format against it.
- `try/except` around anything that can crash QGIS.
- Log the important steps:
  `QgsMessageLog.logMessage("Message", "AI Agent", Qgis.Info)`.
- Do **not** add `# -*- coding: utf-8 -*-` (Python 3 is UTF-8 already).
- Aim for files around 200 lines; the hard cap enforced by tests is 400. Growing
  past the target is a signal to consider extracting a neighbouring module, not
  an automatic failure.
- Keep package `__init__.py` files empty, except the ones that assemble a tool
  list. Convenience re-exports drag extra dependencies at import time.

## Layout and imports

Code lives under `ai_agent/`:

| Package       | Purpose                                                     |
| ------------- | ----------------------------------------------------------- |
| `core/`       | loop, orchestration, LLM transport, state                   |
| `qgis_tools/` | tools by domain — all PyQGIS execution logic                |
| `skills/`     | domain knowledge packages (`SKILL.md`)                      |
| `ui/`         | Qt only: rendering and signals                              |

The plugin is the `ai_agent/` folder as a whole: `__init__.py`,
`metadata.txt`, `icon.svg` and the code inside. Only that folder goes into the
zip and into the QGIS symlink; `tests/`, `tools/`, `docs/` are repository-level
and never reach QGIS. The composition root is `ai_agent/plugin.py`: the
only module allowed to import both `core` and `ui`. The layer direction
(`ui → core → qgis_tools`, never backwards) is guarded by `tests/test_layering.py`.

The target version is **QGIS 4.0+**. On 3.x the plugin does not work and does
not pretend to: the 3.40 LTR build on macOS ships Python 3.9, while the code is
written in 3.10+ syntax (`X | None` annotations). `qgisMinimumVersion` in
`metadata.txt` must match that.

The plugin ships as a zip built by `tools/build_plugin.py`. Everything needed at
runtime must land in the archive — `SKILL.md` files are read from disk, so a
“.py only” package breaks the plugin silently. `tests/test_packaging.py` guards
this.

Imports are absolute only, with the package prefix:
`from ai_agent.ui.dock_widget import ...`. No relative imports
(`from .foo`, `from ..bar`). All imports at the top of the file.

## Verification

```bash
python3 -m unittest discover -s tests -t .
```

Lint and formatting (the same check runs in CI and in the pre-commit hook):

```bash
poetry run ruff check .
poetry run ruff format --check .
```

One-time setup of the hook after cloning:

```bash
poetry install
poetry run pre-commit install
```

Building the installable archive:

```bash
python3 tools/build_plugin.py
```

Updating translations after adding or changing a `tr()` string:

```bash
python3 tools/update_translations.py
```

The command needs no dependencies: extraction parses the AST, compilation is
our own `tools/qm.py` whose output is byte-identical to `lrelease` and pinned
by the `tests/data/golden_ru.qm` fixture. The reasoning for replacing the stock
QGIS recipe lives in [docs/translations.md](docs/translations.md). Two rules
survive here: **a new language needs its plural rules in `NUMERUS_RULES`** (the
compiler refuses unknown languages instead of guessing), and
`tests/test_i18n.py` keeps the catalogue honest — no Russian in sources, no
untranslated entries, placeholders survive, the `.qm` ships while the `.ts`
stays out.

Tests are stdlib `unittest` — not a single dependency. `tests/stub.py` fakes the
`qgis` modules when real QGIS is absent, so the suite runs both on plain Python
and inside the QGIS Python against live PyQGIS. Most names become an inert
`_Stub`, but the **value types are real**: `QColor` does arithmetic, `QLabel`
remembers its text, `QToolButton` its checked state, `QTimer` its start/stop.
That is what makes widgets buildable in tests, so feed behaviour — which
transient survives which event — is checked by running it rather than by
grepping the source. Fake behaviour, never; fake a value, gladly.

What is covered: pure logic (aggregates, expressions, value coercion, UTM zones,
secret scrubbing), both transport protocols, the run transcript, every renderer
type, the tool contract and schemas, skill/registry consistency, the safety
invariant in the loop. Plus `tests/test_sources.py` statically enforces the
style rules: no comments or docstrings, the file-size cap, absolute imports, no
undefined names.

**A new tool or skill means a new test.** Both `describe_style` failures once
survived all the way to live QGIS precisely because nobody called the tool code:
`compileall` and import checks do not catch that.

What tests cannot reach — real PyQGIS calls against layers and Qt painting —
is still checked by hand, following
[docs/smoke_checklist.md](docs/smoke_checklist.md).
