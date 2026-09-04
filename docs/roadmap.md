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
   the existing `qgis_ai_agent` listing. The first public submission is 0.1.0,
   non-experimental.

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
7. **Done — a Gemini preset through its OpenAI-compatible endpoint.** It is
   available alongside the other provider presets and remains on the common
   OpenAI dialect.

## Added along the way

- **A web domain** — `search_web` (with a loud Wikipedia fallback on locked-down
  networks), `fetch_url` and `geocode`; the geocoded bbox feeds `download_osm`
  directly.

## Agent quality — audit 2026-09-03

Found by reading the core end to end, ordered by expected effect on how well
the agent works:

1. **Done 2026-09-03 — retries in the transport.** A single 429, 502/503 or a dropped
   connection ends the run with an error; `core/llm/client.py` and
   `stream_runner.py` make exactly one attempt. Bounded retry with backoff on
   429/5xx and connection resets, with a "retrying…" line in the feed.
2. **Done 2026-09-03 — prompt caching on Anthropic.** The system prompt and the tool schemas
   are identical between the turns of one run and are billed again every turn.
   Mark the static prefix with `cache_control` in `llm/anthropic.py`; keep the
   dynamic tail (plan, queued steps, project context) last so prefix caching on
   OpenAI-style endpoints hits too.
3. **Done 2026-09-03 — the starting project context was thin** — layer names and geometry only,
   so nearly every run spends its first turn on `list_layers`. Add CRS, the
   selected-feature count and, where cheap, feature counts; stay within
   metadata-class data.
4. **Skill loading cost a turn per domain.** Shipped now: the prompt asks for
   one-turn loading and `/skill` preloads before the first turn. Next: let
   `load_skill` take a list of names.
5. **No evaluation harness.** Prompt and skill edits are judged by feel.
   Record real transcripts (tool calls with their results) and replay them
   against the loop with a scripted model — a regression suite for the agent's
   behaviour, and the biggest single lever for "it must work well".
6. **Verification always runs the full round.** A trivial single-step
   non-visual change still costs a 3–4-turn verification; skip or shorten it
   when the batch had one step that a single read can confirm.
7. **Compaction drops, never summarises.** After `KEEP_FULL_RESULTS` older
   results shrink to one-line notes; a summary of the dropped span would keep
   forty-turn runs coherent.
8. **The journal has no numbers.** It records steps, not tokens or wall time
   per turn — the two figures that show where a slow run went.

## Considered and set aside

- **QField / mobile integration** — a different product with its own runtime;
  nothing in the agent loop transfers.
- **Multi-user collaboration** — the agent is a single-user tool by design;
  collaboration belongs to the project storage, not to the assistant.
- **Country-specific statistics integrations** (population forecasting,
  national statistics APIs) — data sources, not agent capabilities; the
  general answer is `add_service_layer`, `run_python` and, where a service
  speaks HTTP, a user-side script.
