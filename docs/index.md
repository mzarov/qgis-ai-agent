# AI Agent

An AI agent inside QGIS 4: it inspects your project and processes data from a
plain-language request. It works as a loop — looks at the project, calls tools,
sees the results, decides the next step. Changes are applied only after you
confirm them.

## What it does

Twelve domains, 65 tools:

| Domain | Example requests |
| --- | --- |
| `inspect` | “what layers do I have?”, “what did I select?”, “show me the map” |
| `project` | “load this file”, “add an OSM basemap”, “load a table from PostGIS” |
| `style` | “make the rivers blue”, “colour by population”, “label with names” |
| `processing` | “build a 500 m buffer”, “clip by the district boundary”, “compute NDVI” |
| `osm` | “download the cafes in Tver”, “roads except unpaved ones from OSM” |
| `edit` | “fix the misspelled name”, “delete the features I selected” |
| `fields` | “add a virtual field with the area in hectares”, “rename nm to name” |
| `layout` | “make an A4 map sheet with a legend and export it to PDF” |
| `python` | the escape hatch: a PyQGIS snippet you read and approve first |
| `web` | “find the EPSG code”, “read this documentation page”, “geocode this place” |
| `annotations` | “mark this place”, “add a note to the map”, “remove that annotation” |
| `three_d` | “open a 3D view of this project” |

On a vision-capable model the agent **sees** the map: it renders the canvas or
a print layout to an image and judges colours, labels and composition by eye.
And after you press Apply it **verifies itself** — re-reads the project,
compares the result with what you asked for and queues fixes when something is
off.

## The safety model

You never watch the agent mutate your project unsupervised:

- **Local reading** tools (listing layers, describing fields, querying data)
  run immediately — they cannot change anything. Their results may still be
  sent to the configured model as part of the agent loop.
- **Network reading** tools wait in a plan for per-call confirmation. A web-only
  batch does not change or snapshot the QGIS project.
- **Writing** tools (styling, processing, loading data) are collected into a
  plan card. Nothing runs until you press **Apply**; **Cancel** discards the
  whole batch.

Arguments are validated at queue time, while the agent is still listening — so
a metre buffer on a degree-based layer is rejected with a ready reprojection
plan instead of producing garbage.

## What it needs

- **QGIS 4.0 or newer.**
- **An account and an API key** with a language-model provider — any
  OpenAI-compatible endpoint or Anthropic. Local servers (Ollama, LM Studio)
  need no key at all.
- Sending a request shares your prompt, recent chat, project notes and basic
  project metadata with the configured endpoint. Sharing sensitive GIS data and
  tool results—feature attribute values, exact map and layer extents, layer
  filters and sources, style categories, Processing and Python results, and
  rendered map or layout images—is a separate option that is off by default.
  Local servers can still store or forward data. Read
  [Data and privacy](privacy.md) before opening a sensitive project.
- Each optional web call is confirmed separately. Search terms go to
  DuckDuckGo or, on fallback, Wikipedia; geocoding goes to the Photon demo or
  custom Nominatim service selected in Settings; and page reads
  contact the approved public HTTPS host. The public OSMF Nominatim instance is
  intentionally not offered. Geocoding starts disabled; Photon permits
  reasonable demo use but may throttle and has no uptime guarantee. Private hosts and credential-bearing URLs are
  rejected. Returned web content is untrusted data, can be forwarded to the
  chosen model and is not cached on disk. This flow is controlled by the
  per-call web confirmation, not by the sensitive-GIS-data option.
- API keys are stored encrypted in the QGIS authentication database, never in
  the project or in the QGIS settings file. The plugin has no external Python
  dependencies at all: install the archive and it runs.

Ready to try? Start with [Setup](SETUP.md), then see [Usage](usage.md) for what
to ask.

## The interface

Available in English and Russian, following the QGIS interface language. The
agent itself replies in whatever language you write to it.
