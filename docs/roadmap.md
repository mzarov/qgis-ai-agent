# Roadmap

Everything below shipped on 2026-08-29, the rename included: the package and
catalogue id are now `ai_agent`, with the display name “AI Agent”.

What comes next, in order. The list was last revised after comparing the
plugin against the QGIS plugin catalogue — in particular the
[GeoGPT AI Agent](https://plugins.qgis.org/plugins/qgis_ai_agent/) listing,
which occupies the old `qgis_ai_agent` slug. That plugin has no released version
and no visible source, so the comparison is against its claims, not its code;
the claims still mark out territory users expect an agent to cover.

## First-release blocker resolved

1. **Done — renamed to `ai_agent`.** The distinct package and catalogue id avoid
   the existing `qgis_ai_agent` listing. The version remains 0.0.1 for the
   initial release.

## Shipped 2026-08-29

2. **Done — analysis recipes in the skills.** Clustering, hotspot detection and
   regression are already reachable through `run_processing`, but the model
   has to guess the right algorithm chain. A recipes section in
   `skills/processing/SKILL.md` — named task, algorithm chain, caveats —
   turns "find hotspots of cafes" into one pass instead of an exploration.
3. **Done — terrain and interpolation guidance.** Same shape as above: DEM slope and
   hillshade, TIN and IDW interpolation as documented chains over the existing
   processing tools.
4. **Done (narrow) — a 3D view domain.** `open_3d_view` opens a named view of
   the current layers when the QGIS build exposes that API. Terrain, camera and
   exaggeration still use the visible, separately approved `run_python` escape
   hatch.
5. **Done — annotations domain.** Text notes and markers live in the project's
   main annotation layer; they can be listed and removed by id.
6. **Done — a run journal.** Applied runs write a plaintext Markdown summary to
   `ai_agent_runs` in the active QGIS profile and report its path. Owner-only
   permissions protect the directory and files where supported; the privacy
   page documents the contents, persistence and cleanup limits.
7. **Done — a tool browser.** A read-only dialog listing every skill and its tools
   with descriptions, so the user can see what the agent can do without
   asking it.
8. **Done — a Gemini preset through its OpenAI-compatible endpoint.** It is
   available alongside the other provider presets and remains on the common
   OpenAI dialect.

## Added along the way

- **A web domain** — `search_web` (with a loud Wikipedia fallback on locked-down
  networks), `fetch_url` and `geocode`; the geocoded bbox feeds `download_osm`
  directly.

## Considered and set aside

- **QField / mobile integration** — a different product with its own runtime;
  nothing in the agent loop transfers.
- **Multi-user collaboration** — the agent is a single-user tool by design;
  collaboration belongs to the project storage, not to the assistant.
- **Country-specific statistics integrations** (population forecasting,
  national statistics APIs) — data sources, not agent capabilities; the
  general answer is `add_service_layer`, `run_python` and, where a service
  speaks HTTP, a user-side script.
