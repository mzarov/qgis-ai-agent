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

The pre-commit hook runs `ruff check --fix` and `ruff format` on every commit —
style and import order are not review topics here, the machine owns them.

Run the fast unit suite (`tests/stub.py` supplies QGIS stand-ins when PyQGIS is
not installed):

```bash
python3 -m unittest discover -s tests -t .
```

For a development install into live QGIS see [docs/SETUP.md](docs/SETUP.md).

## The mental model

The plugin is an agent loop on the Qt main thread. The model calls tools, sees
the results, decides the next step. Reading tools execute immediately; writing
tools queue into a batch the user confirms with one button. Domains are
packaged as skills and load progressively. The full picture is in
[docs/core_architecture.md](docs/core_architecture.md).

```
qgis_ai_agent/   the plugin — the only folder that reaches QGIS
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

The unusual ones first — all of them checked by `tests/test_sources.py`:

- **No comments and no docstrings.** Clarity comes from names, small functions
  and named constants. If a line needs a comment, rename or split instead.
- **English everywhere.** Identifiers, tool descriptions, error messages, docs.
  Russian exists only as a translation catalogue in
  `qgis_ai_agent/translations/`.
- **Files around 200 lines; the hard cap is 400.** Growing past the target is a
  hint to extract a module, not an automatic failure.
- Type hints on every function, absolute imports only, all imports at the top.

The domain-specific ones:

- GUI imports only through `qgis.PyQt`; never `PyQt5`/`PyQt6` directly, no
  `.ui` files.
- All HTTP through `QgsBlockingNetworkRequest` — the QGIS plugin repository
  requires it, and it keeps the UI responsive.
- PyQGIS and Qt objects are touched from the main thread only. Never move tool
  execution into a background thread.
- New dependencies are a last resort: the plugin runs inside the QGIS Python,
  where every extra package is an installation problem for users. Today there
  is exactly one — `keyring`.
- User-facing strings are wrapped in `tr()` with an English literal
  (`tr("Layer '{0}'").format(name)`, never an f-string); model-facing strings
  (tool descriptions, errors) stay plain English without `tr()`. After changing
  them, run `python3 tools/update_translations.py`.

## Adding a tool or a domain

1. `qgis_ai_agent/qgis_tools/<domain>/` — one `BaseTool` subclass per file,
   with `skill`, `safety`, `params_schema`.
2. `qgis_ai_agent/skills/<domain>/SKILL.md` — the domain rules; the `tools`
   list must match the registry.
3. One line in `qgis_tools/registry.py`.

The loop, the orchestrator and the prompt core stay untouched. **A new tool
means a new test** on fake PyQGIS objects — see `tests/test_style_write.py`
for the pattern. The tool contract and schema are checked automatically for
every registered tool.

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

Preview locally with `pip install mkdocs-material mkdocs-static-i18n` and
`mkdocs serve`.

## Before opening a PR

- [ ] `python3 -m unittest discover -s tests -t .` — green
- [ ] `python3 tools/build_plugin.py` — builds
- [ ] a new tool or skill is covered by a test
- [ ] whatever tests cannot reach is added to
      [docs/smoke_checklist.md](docs/smoke_checklist.md)

CI repeats the suite on Python 3.12–3.14, runs ruff, and runs the same
scanners the QGIS plugin repository applies (bandit, detect-secrets). A separate
job runs the import, icon, project-identity and registry smoke checks in the
official QGIS 4 container.

## Making a release

1. Confirm that the display name and Python package identifier are not already
   owned in the official QGIS plugin repository.
2. Update the version in both `metadata.txt` and `pyproject.toml`, and write a
   user-facing changelog entry.
3. Run the full unit, lint, scanner, package and live-QGIS checks. Inspect the
   ZIP and confirm it has one `qgis_ai_agent/` top-level folder.
4. Build twice from the same source and compare SHA-256 hashes. The build uses a
   fixed manifest, timestamps and permissions, so the archives must match.
5. Tag that exact commit, create a GitHub Release and attach the generated plugin
   ZIP rather than a GitHub “Source code” archive. Publish its SHA-256 checksum.
6. Upload the same ZIP to the QGIS repository only after the GitHub release and
   install it once into a clean QGIS profile.
