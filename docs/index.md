# AI Agent

An AI agent inside QGIS 4: it inspects your project and processes data from a
plain-language request. It works as a loop — looks at the project, calls tools,
sees the results, decides the next step. Changes are applied only after you
confirm them.

## What it does

Nine domains, 51 tools:

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

On a vision-capable model the agent **sees** the map: it renders the canvas or
a print layout to an image and judges colours, labels and composition by eye.
And after you press Apply it **verifies itself** — re-reads the project,
compares the result with what you asked for and queues fixes when something is
off.

## The safety model

You never watch the agent mutate your project unsupervised:

- **Reading** tools (listing layers, describing fields, querying data) run
  immediately — they cannot change anything.
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
- Your prompts and short summaries of the project — layer names, field names,
  CRS — are sent to the provider you configure, so pick one you trust. The key
  is stored in the system keychain, never in the project or the settings file.

Ready to try? Start with [Setup](SETUP.md), then see [Usage](usage.md) for what
to ask.

## The interface

Available in English and Russian, following the QGIS interface language. The
agent itself replies in whatever language you write to it.
