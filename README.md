# AI Agent

[![Tests](https://github.com/mzarov/qgis-ai-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/mzarov/qgis-ai-agent/actions/workflows/tests.yml)
[![Documentation](https://github.com/mzarov/qgis-ai-agent/actions/workflows/docs.yml/badge.svg)](https://github.com/mzarov/qgis-ai-agent/actions/workflows/docs.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![QGIS 4.0+](https://img.shields.io/badge/QGIS-4.0%2B-589632.svg)](https://qgis.org/)

AI Agent is a QGIS 4 plugin that works on your project from plain-language
requests. It reads the project, calls tools, looks at the results and decides
the next step. Changes wait in a plan until you press Apply.

It inspects and styles layers, runs Processing, downloads OpenStreetMap and
open data, edits attributes, answers with SQL and charts, and builds print
layouts: nineteen domains, 90 tools.

Documentation: <https://mzarov.github.io/qgis-ai-agent/> (in Russian:
<https://mzarov.github.io/qgis-ai-agent/ru/>).

## Install

QGIS 4.0 or newer is required. Install **AI Agent** from **Plugins → Manage
and Install Plugins**, or download `ai_agent-<version>.zip` from the
[latest release](https://github.com/mzarov/qgis-ai-agent/releases/latest) and
use **Install from ZIP**. The plugin needs no extra Python packages.

## Connect a model

Click the settings button on the panel. Pick a provider or enter the address
of any OpenAI-compatible endpoint; the Anthropic API works too. Enter the
model name and the API key. Local servers such as Ollama and LM Studio need no
key. Keys are stored in the QGIS authentication database.

Everything the agent reads goes to the model you configure; see
[Data and privacy](https://mzarov.github.io/qgis-ai-agent/privacy/).

## Development

```bash
poetry install
poetry run pre-commit install
python3 -m unittest discover -s tests -t .
poetry run ruff check . && poetry run ruff format --check . && poetry run mypy
python3 tools/build_plugin.py
```

The rules for the code are in [CLAUDE.md](CLAUDE.md). See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

GPL-3.0. See [LICENSE](LICENSE).
