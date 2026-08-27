# QGIS AI Agent

An AI agent inside QGIS 4: it inspects your project and processes data from a
plain-language request. It works as a loop — looks at the project, calls tools,
sees the results, decides the next step. Changes are applied only after the user
confirms them.

**Documentation:** <https://mzarov.github.io/qgis-ai-agent/> ·
по-русски: <https://mzarov.github.io/qgis-ai-agent/ru/>

**What it does** — five domains, 25 tools:

| Domain | Example requests |
| --- | --- |
| `inspect` | “what layers do I have?”, “which values does the highway field hold?” |
| `project` | “load this file”, “hide the layer”, “save the project” |
| `style` | “make the rivers blue”, “colour by population”, “label with names” |
| `processing` | “build a 500 m buffer”, “clip by the district boundary”, “compute NDVI” |
| `osm` | “download the cafes in Tver”, “roads except unpaved ones from OSM” |

## Installation

Requires **QGIS 4.0+**. Build the archive and install it through
**Plugins → Manage and Install Plugins → Install from ZIP**:

```bash
python3 tools/build_plugin.py
```

The archive appears in `dist/`. Details, dependencies and the development
install are in [docs/SETUP.md](docs/SETUP.md).

## Configuration

The gear icon on the plugin panel. Picking a provider fills in the address and
the API format — OpenAI, OpenRouter, Anthropic, DeepSeek, Groq, Mistral and the
local Ollama / LM Studio are supported (no key needed for localhost). The key is
stored in the system keychain, not in the config.

The model must support function calling; for endpoints without it there is a
text JSON protocol that switches on by itself.

## How it works

```
user → CoreOrchestrator → AgentLoop (main thread)
                             │  HTTP in background (ModelTurnThread)
                             ▼
                    the model calls tools
               read — immediately │ write — into a batch
                             ▼
                 plan card → the Apply button
```

Three ideas everything rests on:

- **Safety classes instead of “plan → confirm”.** A reading tool runs
  immediately; a writing tool is collected into a batch and waits for the button.
- **Progressive disclosure.** The prompt permanently holds one line per domain;
  the rule bodies and tool schemas are loaded by the `load_skill` meta-tool.
- **Vendor neutrality.** Any OpenAI-compatible API plus the Anthropic dialect;
  no provider SDKs.

The full picture: [docs/core_architecture.md](docs/core_architecture.md).

## Layout

```
qgis_ai_agent/                 the whole plugin — only this folder reaches QGIS
  __init__.py, metadata.txt    the QGIS entry point
  plugin.py                    composition root: wires QGIS, core and ui
  core/                        loop, orchestration, LLM transport, state
  qgis_tools/                  tools by domain — all the PyQGIS logic
  skills/                      domain knowledge (SKILL.md)
  ui/                          Qt only: rendering and signals
tests/                         unittest, runs without QGIS via tests/stub.py
tools/build_plugin.py          builds the installable zip
docs/                          setup, architecture, manual checklist
```

Dependency direction: `ui → core → qgis_tools → skills`; reverse imports are
forbidden and checked by `tests/test_layering.py`.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

Formatting and imports are owned by ruff; set up the pre-commit hook once and it
fixes them on every commit:

```bash
poetry install
poetry run pre-commit install
```

Before a PR, run the same scanners the QGIS plugin repository runs — CI runs
them too:

```bash
pip install bandit detect-secrets ruff
cd qgis_ai_agent && bandit -r . && cd ..
detect-secrets scan qgis_ai_agent/
ruff check . && ruff format --check .
```

The test suite itself has zero dependencies: stdlib only. When real QGIS is
absent, `tests/stub.py` fakes the `qgis` modules — so the suite runs both on
plain Python and inside the QGIS Python.

Code rules live in [CLAUDE.md](CLAUDE.md) and in each package's `CLAUDE.md`.
In short: no comments or docstrings, files around 200 lines (hard cap 400),
type hints everywhere, absolute imports. All of it is enforced by tests, not by
eyeballing reviews.

### Adding a domain

1. `qgis_ai_agent/qgis_tools/<domain>/` — tool classes
   (`skill = "<domain>"`, `safety = read|write`)
2. `qgis_ai_agent/skills/<domain>/SKILL.md` — the domain rules
3. one line in `qgis_tools/registry.py`

The loop, the orchestrator and the prompt stay untouched. A new tool means a new
test against fake PyQGIS objects, as in `tests/test_style_write.py`.

### Before a PR

- [ ] `python3 -m unittest discover -s tests -t .` — green
- [ ] `python3 tools/build_plugin.py` — builds
- [ ] a new tool or skill is covered by a test
- [ ] whatever tests cannot reach is added to
      [docs/smoke_checklist.md](docs/smoke_checklist.md)
