# Installation and configuration

The plugin requires **QGIS 4.0 or newer**. It does not work on QGIS 3.x: the
3.40 LTR build on macOS ships Python 3.9, while the code uses annotation syntax
from Python 3.10.

## 1. Installing from a zip

For a published version, download the `ai_agent-<version>.zip` asset from
the [latest GitHub Release](https://github.com/mzarov/qgis-ai-agent/releases/latest).
Do not pick either of GitHub's auto-generated “Source code” archives: their
top-level folder has the wrong name for a QGIS plugin.

To build the release archive from a checkout instead, run:

```bash
python3 tools/build_plugin.py
```

It writes `dist/ai_agent-<version>.zip` — exactly the shape QGIS expects:
a single `ai_agent/` folder inside the archive.

Then in QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**, pick
the file, press **Install Plugin**. After installation **AI Agent** appears
in the menu.

Do **not** download the zip with GitHub's “Code → Download ZIP” button: that
archive unpacks as a `qgis-ai-agent-main` folder, the folder name becomes the
Python package name, and with a hyphen the plugin will not load.

## 2. API key and address

The plugin works with any OpenAI-compatible endpoint. Open the plugin panel and
press the gear icon:

| Field | What to enter |
| --- | --- |
| Base URL | the address **without** `/chat/completions` — the plugin appends it |
| Model | the model identifier at your provider |
| API key | stored in the QGIS authentication database, not in the QGIS config |
| API format | `auto` — picked from the address; `openai` or `anthropic` manually |
| Authorisation type | `Bearer` for most services, `OAuth` for corporate gateways |
| Verify the SSL certificate | untick only for an internal gateway with a self-signed certificate |

The **Test connection** button sends one short request and shows the model's
reply — proof that the URL, the key and the model name agree with each other.

The first agent run against a remote endpoint asks for explicit consent. In
Settings, **Share project context with the model provider** controls that choice
per endpoint. **Allow sensitive GIS data and tool results** is a separate,
off-by-default permission for feature attribute values, exact map and layer
extents, layer filters and sources, style categories, Processing and Python
results, and rendered map or layout images. The connection test is an
intentional diagnostic request and does not wait for agent-run consent.

Geocoding is disabled by default. In the **Geocoding** card, choose **Photon
demo (fair use)** for occasional interactive lookups or **Custom Nominatim**
and enter a permitted public HTTPS base URL. The model receives only the place
argument; it cannot choose or replace this destination. Every lookup still
waits for its own Apply confirmation.

### Verified providers

The plugin speaks two formats. `auto` picks one from the address, so usually
pasting the URL, the key and the model name is enough.

| Provider | Base URL | Format |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | openai |
| OpenRouter | `https://openrouter.ai/api/v1` | openai |
| Anthropic | `https://api.anthropic.com/v1` | anthropic |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | openai |
| DeepSeek | `https://api.deepseek.com/v1` | openai |
| Groq | `https://api.groq.com/openai/v1` | openai |
| Mistral | `https://api.mistral.ai/v1` | openai |
| Together, Fireworks, Cerebras | the address from their docs | openai |

OpenRouter exposes the models of nearly every vendor through one key and one
address — including Claude and Gemini — and to the plugin it remains an ordinary
OpenAI-compatible service. Setting the format by hand is only needed for a
gateway that speaks the Anthropic format from a non-standard address.

### A local model — no key and no bills

An address on `localhost` requires no key: the field may stay empty. That is how
Ollama, LM Studio, llama.cpp and any other server with an OpenAI-compatible API
connect.

| Server | Base URL |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp server | `http://localhost:8080/v1` |

The plugin treats these addresses as local, but that does not guarantee the
server keeps data on this device. Review whether it stores or forwards requests.

Mind the size: the agent runs a loop over 65 tools, and a small 7–8B
model will get lost in the calls. The sensible minimum is a ~30B-class model
with function calling support.

The agent loop calls tools, so the model must support function calling. If the
endpoint does not, the plugin switches to a text JSON protocol on its own and
remembers the choice for that URL.

## 3. Dependencies

**There are none.** The plugin needs nothing but QGIS itself: install the
archive and it runs. Keys live in the QGIS authentication database, so no
external Python library is involved in storing them.

Network requests stay on the QGIS network stack: ordinary calls use
`QgsBlockingNetworkRequest`, while streaming and the pinned web transport use
`QgsNetworkAccessManager` with a nested event loop. The latter accepts only
public DNS answers, pins checked IPs on direct routes while TLS verifies the
original host, preserves the hostname through an explicit QGIS proxy, and
follows only manually validated same-origin redirects; a direct-route mismatch
is blocked rather than bypassed.

The first time a key is saved, QGIS asks for its **master password** — the same
one it uses for layer and PostGIS passwords. If you cancel that dialog the key
stays locked and the settings window says so.

Before connecting a project to a remote provider, read
[Data and privacy](privacy.md). Tool results sent to the model can contain
attribute values, exact map or layer extents, layer filters and sources, style
categories, Processing or Python results, and rendered map or layout images—not
just basic schema metadata.

## 4. Development install

To avoid rebuilding the archive on every edit, symlink the package from the
repository into the profile's plugin folder.

The folder path: **Settings → User Profiles → Open Active Profile Folder**,
then `python/plugins`.

```bash
PLUGINS_DIR="$HOME/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins"
mkdir -p "$PLUGINS_DIR"
ln -sfn "$(pwd)/ai_agent" "$PLUGINS_DIR/ai_agent"
```

The link points at the package folder, not the repository root: only the plugin
reaches QGIS, without tests and docs. If your symlink still points at the
repository root from the old layout — recreate it with this command, otherwise
QGIS stops seeing the plugin.

While editing code, reload the plugin with **Plugin Reloader** (`Ctrl+F5`). If
the package structure changed, a full QGIS restart is needed: unticking the
plugin does not unload submodules from `sys.modules`. The Python console keeps
its own cache; reset it with:

```python
import sys; [sys.modules.pop(n) for n in list(sys.modules) if n.startswith("ai_agent")]
```

## 5. Verification

```bash
python3 -m unittest discover -s tests -t .
```

The command above is the fast unit suite and uses QGIS stand-ins when PyQGIS is
absent. CI also runs a focused import, icon and registry smoke test in the
official QGIS 4 container. Full workflows against live layers and the QGIS UI
are checked by hand following [smoke_checklist.md](smoke_checklist.md).
