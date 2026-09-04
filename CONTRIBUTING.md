# Contributing

Thanks for looking into the project. It is deliberately small and strict: most
rules are enforced by tests, so the fastest way to a green PR is to know them
up front.

## Getting started

```bash
git clone https://github.com/mzarov/qgis-ai-agent.git
cd qgis-ai-agent
poetry install
poetry run pre-commit install
```

Use Python 3.12 or newer and Poetry 2.1.3. Poetry installs development tools
from `poetry.lock` in dependency-only mode; it does not build or install the
QGIS plugin. `python3 tools/build_plugin.py` builds the installable plugin ZIP.
CI runs this same fresh-clone setup on each supported Python version.

The pre-commit hook runs `ruff check --fix` and `ruff format` on every commit.
Ruff also checks undefined names; do not maintain a second Python name resolver
in the test suite.

Run the fast unit suite (`tests/stub.py` supplies QGIS stand-ins when PyQGIS is
not installed):

```bash
python3 -m unittest discover -s tests -t .
```

CI publishes the `fast-suite-branch-coverage` artifact with XML and HTML reports.
To generate the same report locally, run
`poetry run coverage run -m unittest discover -s tests -t .`, then
`poetry run coverage html` and open `build/coverage/index.html`. Coverage measures
production Python executed by the fast suite with QGIS substitutes. It does not
include the separate real-QGIS processes or establish API compatibility. Use
missing branches to select meaningful regressions; there is no percentage gate.

For a development install into live QGIS see [docs/SETUP.md](docs/SETUP.md).

## The mental model

The plugin is an agent loop on the Qt main thread. The model calls tools, sees
the results, decides the next step. Local reading tools execute immediately;
network reads and writes queue into a batch the user confirms. A web-only batch
does not take a project snapshot. Domains are packaged as skills and load
progressively. The full picture is in
[docs/core_architecture.md](docs/core_architecture.md).

```
ai_agent/   the plugin — the only folder that reaches QGIS
  core/          loop, orchestration, LLM transport, state
  qgis_tools/    tools by domain — all the PyQGIS logic
  skills/        domain knowledge (SKILL.md)
  ui/            Qt only: rendering and signals
tests/  tools/  docs/   repository level, never shipped
```

Layer direction is `ui → core → qgis_tools → skills` and is enforced by
`tests/test_layering.py`. Each package has its own `CLAUDE.md` with the local
rules — read the one you are about to touch.

## Code rules

- **Explain contracts and reasons.** Prefer clear names and small functions.
  Concise docstrings describe public inputs, results, errors and side effects;
  comments explain non-obvious Qt lifetime, threading and data-integrity rules.
  Avoid comments that repeat the code.
- **English in source and contributor documentation.** Russian belongs in the
  translation catalogue and the `docs/*.ru.md` mirrors.
- **Keep modules cohesive.** Around 200 lines is a useful review prompt, not a
  limit. Split by responsibility and dependency boundaries, not by line count.
- Type hints on every function, absolute imports only, all imports at the top.
  `tests/test_sources.py` checks return annotations and absolute imports.
- Run `poetry run mypy`. Strict checking currently covers `config/`, `skills/`,
  the `BaseTool` contract, argument validation and Processing effect policy, as listed in
  `pyproject.toml`. QGIS imports are the only missing-import exception. The rest
  of the application is not yet strictly checked; grow this boundary as modules
  gain stable typed contracts, without broad `Any` or blanket suppressions.

The domain-specific ones:

- GUI imports only through `qgis.PyQt`; never `PyQt5`/`PyQt6` directly, no
  `.ui` files.
- All HTTP stays on the QGIS network stack — never `requests`. Ordinary calls
  use `QgsBlockingNetworkRequest`; streaming and web redirects use
  `QgsNetworkAccessManager` with a nested event loop. Web DNS answers must all
  be public; one validated IP is pinned while TLS verifies the approved host.
  Only manually validated, same-origin redirects are followed, and a proxy-route
  mismatch fails closed.
- PyQGIS and Qt objects are touched from the main thread only. Never move tool
  execution into a background thread.
- New dependencies are a last resort: the plugin runs inside the QGIS Python,
  where every extra package is an installation problem for users. Today there
  are none at all.
- User-facing strings are wrapped in `tr()` with an English literal
  (`tr("Layer '{0}'").format(name)`, never an f-string); model-facing strings
  (tool descriptions, errors) stay plain English without `tr()`. After changing
  them, run `python3 tools/update_translations.py`.

## Adding a tool or a domain

1. `ai_agent/qgis_tools/<domain>/` — a `BaseTool` subclass with `skill`,
   `params_schema`, and explicit `safety`, `egress`, `external_effect` and
   `network_access` declarations. `egress` classifies every returned value;
   `external_effect` identifies changes a project snapshot cannot restore;
   `network_access` identifies service calls, including reads. Override the
   parameter-dependent capability methods when the effect depends on arguments.
2. Register the class in `<domain>/__init__.py`, and a new domain list in
   `qgis_tools/registry.py`.
3. `ai_agent/skills/<domain>/SKILL.md` — the domain rules; the `tools` list must
   match the registry. Update public capability counts and both documentation
   languages when adding a domain.

`prepare` validates and normalizes arguments without mutating the project or
contacting services. It must bind selected layers by ID so the later execution
cannot silently target a different layer. `execute` runs on the Qt main thread,
returns JSON-compatible values and reports partial effects accurately. Raise
clear English errors with a recovery hint; `summarize_call` must tolerate
malformed arguments and uses translated user-facing text. See the complete
contract example in `ai_agent/qgis_tools/CLAUDE.md`.

For Processing, add built-in algorithms that modify existing sources to
`qgis_tools/processing/effects.py::SOURCE_WRITERS` and cover their confirmation
and snapshot implications. Unknown providers, scripts and models receive the
conservative effect policy.

The loop, the orchestrator and the prompt core should remain unchanged for a
new domain. **A new tool means a behavioral test** — see
`tests/test_style_write.py`. Exercise success, invalid input and failures after
an effect. Add real-QGIS workflow coverage when relying on a new PyQGIS API;
source-text assertions cannot establish runtime behavior. The contract,
capability declarations and schema are checked for every registered tool.

## Documentation map

Two layers, two readers — never duplicate between them:

- **`CLAUDE.md`** (root and per package) — the agent layer: rules and
  invariants for AI-assisted work on the code. Always loaded into context, so
  it stays terse and English-only. Long rationale lives in `docs/` and is
  linked from the rule.
- **`docs/`** — the human layer, published as a bilingual MkDocs site. The
  English page is the original (`page.md`); its Russian twin sits next to it
  (`page.ru.md`). **When you edit one, mirror the other** —
  `tests/test_docs.py` fails on an orphan.

Preview locally with `poetry install --with docs` and `poetry run mkdocs serve`.
Run `poetry run mkdocs build --strict` before a documentation PR. CI builds
changed documentation on pull requests and deploys only from `main`.

## Before opening a PR

- [ ] `python3 -m unittest discover -s tests -t .` — green
- [ ] `poetry run ruff check .` and `poetry run ruff format --check .` — green
- [ ] `poetry run mypy` — strict boundary checks pass
- [ ] `python3 tools/build_plugin.py` — builds
- [ ] a new tool or skill is covered by a test
- [ ] whatever tests cannot reach is added to
      [docs/smoke_checklist.md](docs/smoke_checklist.md)

CI repeats the suite on Python 3.12–3.14, runs ruff, and runs the same
scanners the QGIS plugin repository applies (bandit, detect-secrets). A separate
job runs installed-package smoke checks and real layer, Processing, layout and
Qt lifecycle workflows in the official QGIS 4 containers. The unit suite remains
useful without QGIS; live workflows validate the API contracts that substitutes
cannot guarantee.

## Making a release

1. Confirm that the display name and Python package identifier are not already
   owned in the official QGIS plugin repository.
2. Update the version in both `metadata.txt` and `pyproject.toml`, and write a
   user-facing changelog entry.
3. Run the full unit, lint, scanner, package and live-QGIS checks. Inspect the
   ZIP and confirm it has one `ai_agent/` top-level folder.
4. Build twice from the same source and compare SHA-256 hashes. The build uses a
   fixed manifest, timestamps and permissions, so the archives must match.
5. Tag that exact commit, create a GitHub Release and attach the generated plugin
   ZIP rather than a GitHub “Source code” archive. Publish its SHA-256 checksum.
6. Upload the same ZIP to the QGIS repository only after the GitHub release and
   install it once into a clean QGIS profile.
