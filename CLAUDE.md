# AI Agent

A plugin for QGIS 4 LTR: an AI agent that inspects the project and processes data from a
plain-language request.

Domains are implemented as skills: `inspect`, `project`, `style`, `processing`, `osm`,
`data`, `draw`, `edit`, `fields`, `layout`, `python`, `web`, `annotations`, `three_d`,
`tables`, `sql`, `charts`, `plugins`, `quality`. Each `skills/<domain>/SKILL.md` says
what its domain covers. Invariants to know up front:

- `python` (`run_python`) is the escape hatch to the whole QGIS API. It is destructive,
  so the user reads the code first. It is a permanent part of the design: never propose
  cutting it for review reasons
  ([why](docs/core_architecture.md#the-python-escape-hatch)).
- The `destructive` class also covers in-place attribute edits and deletion (`edit`,
  `fields`) and running or installing another plugin (`plugins`).
- `web` makes only confirmed public-HTTPS calls. `data` sources are grouped into
  connectors the user can switch off.
- `sql` runs one read-only SELECT through the virtual layer provider, or keeps the query
  as a live virtual layer.
- A `charts` spec rides beside the tool result and never reaches the model.
- `quality` fixes stay queued Processing steps that write new layers.

After the user applies a batch, the orchestrator starts a verification run: the agent
re-reads the result with read tools and, for visual changes, looks at a rendered image.
A batch whose every step reads back as done through its tool's `confirm_applied` skips
that run.

Architecture and prompt design belong to the user; implementation belongs to the agent.
Do not ask permission for routine decisions — write the code.

## Stack

- GUI **only** through the QGIS wrapper (`from qgis.PyQt.QtWidgets import QWidget`),
  never `PyQt5`, `PyQt6`, `PySide2` or `PySide6` directly. No Qt Designer, no `.ui`
  files: the interface is built in code.
- LLM: any OpenAI-compatible REST API (plus the Anthropic dialect). Vendor neutrality is
  a principle: no SDK tied to one provider.
- Secrets live only in the QGIS authentication database (`QgsAuthManager`), never in
  config. An address on `localhost` needs no key, so local servers (Ollama, LM Studio)
  work without one.
- Dependencies: Poetry, Python 3.12+. The plugin runs inside QGIS, so every new
  dependency is an installation problem for the user. Today there are none; add one only
  when strictly necessary.
- **All HTTP stays on the QGIS network stack**, never `requests`. Ordinary calls use
  `QgsBlockingNetworkRequest`; streaming uses `QgsNetworkAccessManager` with a nested
  event loop; both only through `qgis_tools/common/network.py::send`, which defuses the
  GIL deadlock a worker thread can otherwise hit. Web redirects keep their own
  main-thread loop. Web requests validate all DNS answers, try pinned public IPs while
  verifying the original TLS host, and follow only manually checked same-origin
  redirects. An explicit QGIS proxy receives the original hostname; direct-route
  mismatches fail closed.

## Architecture

Details and reasoning: [docs/core_architecture.md](docs/core_architecture.md).

1. **No backend.** All logic lives inside the plugin. No agent framework: the loop is
   our own.
2. **Agent loop.** UI emits signals → `CoreOrchestrator` → `AgentLoop`. The loop works
   act → observe → decide: the model calls tools, sees results, picks the next step. It
   is **not** a one-shot planner. A run ends when the model replies without tool calls.
3. **Safety classes instead of "plan → confirm".** Every tool declares `safety`:
   - `read` executes immediately unless it declares `network_access`
   - `write` is collected into a batch and applied after the user presses the button, or
     at once in Auto mode (never a destructive batch, never after a failure). Plan mode
     offers read tools only and refuses any other call.
   - `destructive` is reserved for per-call confirmation

   A write call returns `{"status": "queued"}` to the model: that is success, not an
   error. A network read also queues, pauses automatically for exact per-call consent,
   and skips the project snapshot when the batch contains no mutation.
4. **A tool and a skill are different things; do not mix the words:**
   - **tool**: one `BaseTool` subclass in `qgis_tools/<domain>/`, one class per file
   - **skill**: a domain package `skills/<domain>/SKILL.md` with frontmatter (`name`,
     `description`, `tools`) and a body of domain rules
5. **Progressive disclosure.** The system prompt permanently holds one line per skill.
   The `SKILL.md` body and the tool schemas load when the model calls `load_skill`.
   **Never add a domain rule to `core/agent/prompts.py`**; only domain-independent
   behaviour lives there.
6. **A new domain is added with files, not by editing orchestration:**
   `qgis_tools/<domain>/` + `skills/<domain>/SKILL.md` + one line in
   `qgis_tools/registry.py`.

## Main thread — critical

PyQGIS and Qt objects may be touched **only from the main thread**. So the agent loop is
a state machine on the main thread: the outgoing HTTP request runs in `ModelTurnThread`,
while `_on_turn` and tool execution run as main-thread slots.

A long step may hand **only its heavy part** to a QGIS task (`BaseTool.start`,
`qgis_tools/common/background.py`): a Processing algorithm through
`QgsProcessingAlgRunnerTask`, a download through `common/network.py::send`. The task
touches only thread-safe objects; the project, layers and widgets are touched when it
ends, on the main thread, and the apply run waits for its signal without blocking
(`core/agent/apply_run.py`). Never move a whole tool or the loop to a background thread,
and never rewrite the loop as a background `while` or as `asyncio`: that crashes QGIS.

## PyQGIS — do not hallucinate

- The QGIS 4 API is entirely different from QGIS 2. `QgsComposition` does not exist.
- Project state: always through `QgsProject.instance()`.
- Processing: `QgsApplication.processingRegistry()`, the `processing` module.
- Layouts: `QgsLayout`, `QgsProject.instance().layoutManager()`.
- Unsure about a PyQGIS method? Look it up in the "PyQGIS Developer Cookbook 3.40"
  first, then write the code.

## Language

- **The repository speaks English, all of it:** code, identifiers, tool schemas, system
  prompts, `SKILL.md`, error messages, UI text, README, docs, CLAUDE.md files. Russian
  lives in exactly two places: the translation catalogue in `ai_agent/translations/` and
  the `docs/*.ru.md` twin of every `docs/*.md`. `tests/test_i18n.py` enforces the source
  side.
- **Documentation has two layers.** `CLAUDE.md` files are the agent layer: rules and
  invariants, always in context, terse, English only. `docs/` is the human layer: the
  bilingual MkDocs site. Long rationale belongs in `docs/` with a link from the rule,
  never in both. When editing a `docs/*.md`, mirror the change in its `*.ru.md` twin.
- **User-facing text is wrapped in `tr()`, model-facing text is not.** `summarize_call`
  and `ui/` are read by a person, so `tr("Apply")`. Tool `description`s, schemas and
  errors are read by the model, so plain English; piping them through `tr()` would send
  the model Russian schemas.
- `tr()` takes a string literal only: `tr("Layer '{0}'").format(name)`, never an
  f-string, which `update_translations.py` cannot extract.

## Code style

- Prefer clear names and small functions. No docstrings. A comment is one short line,
  and only where code that looks right would be wrong without it: Qt lifetime, threads,
  cancellation, Undo, data integrity, security. Long reasoning goes to `docs/`.
- Magic values become named module constants (`SUSPICIOUS_DEGREES`, `DEFAULT_STEPS`,
  `MAX_DAY_AGE`).
- PEP 8, type hints everywhere:
  `def execute(self, params: dict[str, Any]) -> dict[str, Any]:`.
- Formatting and import order are owned by **ruff** (`ruff format` +
  `ruff check --fix`), wired as a pre-commit hook. Do not hand-format against it.
- `try/except` around anything that can crash QGIS.
- Log the important steps:
  `QgsMessageLog.logMessage("Message", "AI Agent", Qgis.MessageLevel.Info)`.
- Do **not** add `# -*- coding: utf-8 -*-`.
- Aim for cohesive modules, often around 200 lines. Review larger modules for distinct
  responsibilities; do not split a cohesive unit just for a line count.
- Keep package `__init__.py` files empty, except the ones that assemble a tool list.
  Convenience re-exports drag extra dependencies at import time.

## Layout and imports

Code lives under `ai_agent/`: `core/` (loop, orchestration, LLM transport, state),
`qgis_tools/` (tools by domain, all PyQGIS execution logic), `skills/` (`SKILL.md`
packages), `ui/` (Qt only: rendering and signals) and `config/` (settings both sides
read; it imports no other layer). `ai_agent/plugin.py` is the composition root, the only
module allowed to import both `core` and `ui`. The layer direction
`ui → core → qgis_tools` never goes backwards, and tool domains do not import each
other (`tests/test_layering.py`).

Imports are absolute with the package prefix (`from ai_agent.ui.dock_widget import ...`),
never relative, all at the top of the file. `tests/test_sources.py` guards this and the
return annotations.

The plugin is the `ai_agent/` folder as a whole (`__init__.py`, `metadata.txt`,
`icon.svg` and the code). Only that folder goes into the zip and the QGIS symlink;
`tests/`, `tools/` and `docs/` never reach QGIS. The zip is built by
`tools/build_plugin.py` and must hold everything needed at runtime: `SKILL.md` files are
read from disk, so a ".py only" package breaks the plugin silently
(`tests/test_packaging.py`).

The target is **QGIS 4.0+**, matching `qgisMinimumVersion` in `metadata.txt`. The code
uses Python 3.10+ syntax (`X | None`), and the 3.40 LTR build on macOS ships Python 3.9,
so QGIS 3.x is not supported.

## Verification

```bash
python3 -m unittest discover -s tests -t .
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

CI and the pre-commit hook run the same checks. Strict mypy covers the files under
`[tool.mypy]` in `pyproject.toml`, exempting only unavailable QGIS imports; grow that
scope as contracts become stable. Ruff owns undefined-name checking. Poetry is
dependency-only: after cloning, run `poetry install` and
`poetry run pre-commit install`. `python3 tools/build_plugin.py` builds the installable
archive.

Releasing is the `release` workflow in GitHub Actions. Bump the version only when the
user decides to release ([docs/releasing.md](docs/releasing.md)).

After adding or changing a `tr()` string, run `python3 tools/update_translations.py`. It
needs no dependencies: extraction parses the AST, and `tools/qm.py` compiles output
byte-identical to `lrelease`, pinned by `tests/data/golden_ru.qm`
([why](docs/translations.md)). **A new language needs its plural rules in
`NUMERUS_RULES`**: the compiler refuses unknown languages. `tests/test_i18n.py` keeps
the catalogue honest: no Russian in sources, no untranslated entries, placeholders
survive, the `.qm` ships and the `.ts` stays out.

### Tests

Tests are stdlib `unittest`, with no dependencies. `tests/stub.py` fakes the `qgis`
modules when QGIS is absent, so the suite runs on plain Python and in the QGIS Python.
Most names become an inert `_Stub`, but value types are real (`QColor`, `QLabel`,
`QToolButton`, `QTimer` keep their state), so behaviour is checked by running widgets,
not by grepping the source. Fake behaviour, never; fake a value, gladly. CI records
fast-suite branch coverage: use missing branches for targeted regressions, not as a quota.

- **A new tool or skill means a new test** that calls the tool code; import checks do
  not catch a broken tool.
- **A new skill also brings eval cases:** `skills/<domain>/evals/cases.yaml` next to its
  `SKILL.md`, plus a routing case in `evals/routing.yaml`. After editing a `SKILL.md`, a
  tool description or the prompt core, run the touched suite (`python3 evals/run.py`);
  after changing a tool's behaviour, Apply or verification, run the agent bench
  (`python3 evals/run.py --agent`). In CI they run only by hand or with the
  `skill-evals` label and fail a suite below its floor in `evals/thresholds.json`
  ([docs/skill_evals.md](docs/skill_evals.md)).
- A user-visible flow change (send, apply, stop, undo, verification, composer) needs a
  scenario in `tests/real_qgis_e2e.py`, which runs the whole plugin against the scripted
  model in `tests/e2e_model.py`. The release workflow is gated on it.
- A UI change means regenerated goldens for `tests/real_qgis_visual.py` (English JSON
  structure, clipped text in both languages, pixels in the pinned `ui-pixels` CI job).
- `tests/real_qgis_live.py` checks outcomes with a real model and spends money: it runs
  only by hand or from the release workflow, never on push or pull requests.
- `real_qgis_live` and `real_qgis_e2e` fail above their ceilings in
  `tests/data/token_ceilings.json`. A change that moves spending on purpose refreshes
  them with `tests/token_ceilings.py`.

`tests/real_qgis_smoke.py` checks the installed ZIP; `tests/real_qgis_workflows.py` runs
live layer and Qt lifecycle workflows and the suites above. Regenerating goldens,
refreshing ceilings and the manual checks are in
[docs/smoke_checklist.md](docs/smoke_checklist.md).
