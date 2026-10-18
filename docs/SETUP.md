# Setup

The plugin needs **QGIS 4.0 or newer**. It does not run on QGIS 3.x.

## 1. Install

Install **AI Agent** from **Plugins → Manage and Install Plugins**.

To install a specific version, download `ai_agent-<version>.zip` from the
[GitHub releases](https://github.com/mzarov/qgis-ai-agent/releases/latest) and
use **Install from ZIP** in the same dialog. Do not use GitHub's "Source code"
or "Download ZIP" archives: their folder name is not a valid plugin name.

To build the archive from a checkout, run `python3 tools/build_plugin.py`. It
writes `dist/ai_agent-<version>.zip`.

The plugin has no Python dependencies beyond QGIS.

## 2. Connect a model

Open the panel and click the settings button. On the **Connection** page pick a
provider tile or enter your own address:

- **Server address**: the base URL, without `/chat/completions`.
- **Model**: the model name at your provider.
- **API key**: stored encrypted in the QGIS authentication database, not in a
  settings file. The first time you save a key, QGIS asks for its master
  password.

**Test connection** sends one short request and shows the reply. It also
checks whether the model can see pictures; if not, the agent checks its work
by reading data instead of looking at a rendered map. Test again after you
change the model.

The API format (`auto`, `openai` or `anthropic`) and the authorisation type are
on the **Advanced** page. `auto` picks the format from the address.

The model must support function calling. If the endpoint does not, the plugin
switches to a text JSON protocol on its own. A model of about 30B parameters or
larger works best; small 7–8B models often get the tool calls wrong.

### Providers

| Provider | Server address |
| --- | --- |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Anthropic | `https://api.anthropic.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Mistral | `https://api.mistral.ai/v1` |

Any other OpenAI-compatible service works with its own address.

### Local models

An address on `localhost` needs no key.

| Server | Server address |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp server | `http://localhost:8080/v1` |

A local server keeps requests on your computer only if it is configured to;
check whether it logs or forwards them.

### Geocoding

Geocoding is off by default. On the **Geocoding** page choose the Photon demo
service for occasional lookups, or your own Nominatim server. Each lookup asks
for confirmation first.

Before you connect a remote provider, read [Data and privacy](privacy.md).

## 3. Development install

Link the package folder into your QGIS profile instead of rebuilding the ZIP.
Find the profile with **Settings → User Profiles → Open Active Profile
Folder**; plugins live in `python/plugins`.

```bash
PLUGINS_DIR="$HOME/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins"
mkdir -p "$PLUGINS_DIR"
ln -sfn "$(pwd)/ai_agent" "$PLUGINS_DIR/ai_agent"
```

Link `ai_agent/`, not the repository root. Reload the plugin with **Plugin
Reloader**. After you add or move modules, restart QGIS.

## 4. Tests

```bash
python3 -m unittest discover -s tests -t .
poetry install
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

The unit suite runs on plain Python with QGIS stand-ins from `tests/stub.py`.
For branch coverage, run `poetry run coverage run -m unittest discover -s tests -t .`
and `poetry run coverage html`.

The real-QGIS suites need the QGIS Python. On macOS:

```bash
R=/Applications/QGIS-final-4_2_1.app/Contents
cd tests && QT_QPA_PLATFORM=offscreen PYTHONHOME=$R/Resources \
  PYTHONPATH=$R/Resources/python3.12:$R/Resources/python3.12/lib-dynload:$R/Resources/python3.12/site-packages \
  $R/MacOS/python3.12 real_qgis_workflows.py
```

See the [smoke checklist](smoke_checklist.md) for the other suites and the
manual checks.

Provider logos come from [Simple Icons](https://simpleicons.org) (CC0) and
remain their owners' trademarks; interface icons are
[Lucide](https://lucide.dev) (ISC).
