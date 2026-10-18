# Contributing

Most rules are enforced by tests, so read them before you start:

- [CLAUDE.md](CLAUDE.md) holds the rules and invariants for the whole
  repository; each package under `ai_agent/` has its own `CLAUDE.md`.
- [docs/core_architecture.md](docs/core_architecture.md) explains how the agent
  works.
- [docs/SETUP.md](docs/SETUP.md) covers the development install into QGIS.

## Setup

Use Python 3.12 or newer and Poetry 2.1.3.

```bash
git clone https://github.com/mzarov/qgis-ai-agent.git
cd qgis-ai-agent
poetry install
poetry run pre-commit install
```

Poetry installs only the development tools. The pre-commit hook runs
`ruff check --fix` and `ruff format`.

## Adding a tool or a domain

1. Add a `BaseTool` subclass in `ai_agent/qgis_tools/<domain>/`, one class per
   file, with `skill`, `params_schema` and explicit `safety`, `egress`,
   `external_effect` and `network_access`.
2. Register it in `<domain>/__init__.py`; a new domain also gets one line in
   `qgis_tools/registry.py`.
3. Write the rules in `ai_agent/skills/<domain>/SKILL.md`, and the eval cases
   in `skills/<domain>/evals/cases.yaml` (see
   [docs/skill_evals.md](docs/skill_evals.md)).
4. Add a behavioural test. Update the public tool counts in both documentation
   languages.

## Before opening a pull request

- [ ] `python3 -m unittest discover -s tests -t .` passes
- [ ] `poetry run ruff check .`, `poetry run ruff format --check .` and
      `poetry run mypy` pass
- [ ] `python3 tools/build_plugin.py` builds
- [ ] a new tool or skill has a test
- [ ] a documentation change passes `poetry run mkdocs build --strict`
      (`poetry install --with docs` first), and every `docs/*.md` change is
      mirrored in its `docs/*.ru.md` twin
- [ ] what tests cannot reach is added to
      [docs/smoke_checklist.md](docs/smoke_checklist.md)

Follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report security issues
as described in [SECURITY.md](SECURITY.md).
