# Roadmap

What comes next, in order. The list was last revised after comparing the
plugin against the QGIS plugin catalogue — in particular the
[GeoGPT AI Agent](https://plugins.qgis.org/plugins/qgis_ai_agent/) listing,
which occupies the `qgis_ai_agent` slug. That plugin has no released version
and no visible source, so the comparison is against its claims, not its code;
the claims still mark out territory users expect an agent to cover.

## Blocking the first release

1. **Rename before publishing.** The catalogue slug `qgis_ai_agent` is taken.
   The plugin needs a distinct name and package id before the first
   submission; the version stays 0.0.1 until then.

## Planned

2. **Analysis recipes in the skills.** Clustering, hotspot detection and
   regression are already reachable through `run_processing`, but the model
   has to guess the right algorithm chain. A recipes section in
   `skills/processing/SKILL.md` — named task, algorithm chain, caveats —
   turns "find hotspots of cafes" into one pass instead of an exploration.
3. **Terrain and interpolation guidance.** Same shape as above: DEM slope and
   hillshade, TIN and IDW interpolation as documented chains over the existing
   processing tools.
4. **A 3D view domain.** QGIS ships 3D map views; the agent cannot open or
   configure one. A small `three_d` domain — create a view, set the terrain,
   camera and exaggeration — covers the visible gap.
5. **Annotations domain.** Text, arrows and highlights on the map through the
   QGIS annotation layers, so "mark this district" has a first-class answer.
6. **A run journal.** The QGIS message log already records every step, but it
   scrolls away. A per-run journal — what was asked, what ran, what changed,
   exportable as a file — is the honest version of "audit logging".
7. **A tool browser.** A read-only dialog listing every skill and its tools
   with descriptions, so the user can see what the agent can do without
   asking it.
8. **Gemini through its OpenAI-compatible endpoint.** Likely already works via
   a custom address; verify it and add a provider preset if it does.

## Considered and set aside

- **QField / mobile integration** — a different product with its own runtime;
  nothing in the agent loop transfers.
- **Multi-user collaboration** — the agent is a single-user tool by design;
  collaboration belongs to the project storage, not to the assistant.
- **Country-specific statistics integrations** (population forecasting,
  national statistics APIs) — data sources, not agent capabilities; the
  general answer is `add_service_layer`, `run_python` and, where a service
  speaks HTTP, a user-side script.
