# Smoke checklist

Most behaviour is covered by automated tests. This page holds the procedures
for the real-QGIS suites and a short list of checks that still need a person.

## Automated suites

- `python3 -m unittest discover -s tests -t .` is the fast suite. It runs
  without QGIS.
- `tests/real_qgis_smoke.py` installs the built ZIP into a real QGIS.
- `tests/real_qgis_workflows.py` runs live layer, Processing and Qt lifecycle
  workflows, the screen checks and `tests/real_qgis_e2e.py`.
- `tests/real_qgis_e2e.py` drives the whole plugin the way a person does: it
  types a request, sends it, applies, stops and undoes. The model is
  `tests/e2e_model.py`, a scripted OpenAI-compatible server on `127.0.0.1`
  that records every request.

To add an end-to-end scenario, subclass `ScenarioCase`, queue model turns with
`say()`, `call()`, `calls()` and `fail()`, then drive the panel with `ask()`,
`apply()` and `wait_idle()`. A scenario fails on an unexpected request or an
unused scripted turn. Run the suites with the QGIS Python:

```bash
QT_QPA_PLATFORM=offscreen python3 tests/real_qgis_workflows.py
```

## Screen goldens

`tests/real_qgis_visual.py` builds every screen without a model and checks it
three ways: widget structure against JSON goldens in `tests/data/ui/structure`
(English only), clipped text and overflow in English and Russian
(`UI_LOCALE=ru`), and pixels against PNG goldens in `tests/data/ui/pixels`.
Pixels are compared only in the `ui-pixels` CI job, on one QGIS image pinned
by digest. Every CI run attaches an `index.html` gallery of the screens.

After an intended UI change, rewrite the structure goldens and review the JSON
diff:

```bash
UI_UPDATE_GOLDENS=1 QT_QPA_PLATFORM=offscreen python3 tests/real_qgis_workflows.py real_qgis_visual
```

Pixel goldens come only from the pinned image, never from a desktop QGIS.
Either copy the `ui-actual` images from the `ui-pixels` artifact of the failed
run into `tests/data/ui/pixels`, or run the same image locally:

```bash
docker run --rm --platform linux/amd64 -v "$PWD":/repo -w /repo \
  -e QT_QPA_PLATFORM=offscreen -e UI_PIXEL_BASELINE=1 -e UI_UPDATE_GOLDENS=1 \
  qgis/qgis@sha256:23c12670e69909e8659a5c098aa307996735a5763b9ff9c3268bdeeee1a10916 \
  sh -c 'python3 tests/real_qgis_workflows.py real_qgis_visual && UI_LOCALE=ru python3 tests/real_qgis_workflows.py real_qgis_visual'
```

## Live-model scenarios

`tests/real_qgis_live.py` gives a real model ordinary tasks: a graduated
style, a counting question, labels, a metric buffer. It checks only the
outcome, because the model chooses its own route. A failure means a prompt,
skill or tool schema misleads real models, or the provider changed.

The `live-model` workflow runs it in QGIS CI. It never runs on push or pull
requests: start it from the Actions tab, or tick **live_model_check** when
running a release. It needs the `LIVE_MODEL_URL` and `LIVE_MODEL` variables
and the `LIVE_MODEL_KEY` secret. Spending is capped per run, per suite and by
the job timeout; also set a spending limit at the provider.

Locally, any OpenAI-compatible server works, at no cost with a local model:

```bash
LIVE_MODEL_URL=http://localhost:11434/v1 LIVE_MODEL=qwen3 LIVE_MODEL_KEY=local \
  QT_QPA_PLATFORM=offscreen python3 tests/real_qgis_workflows.py real_qgis_live
```

## Token ceilings

Two checks compare spending with `tests/data/token_ceilings.json`:

- **Scripted, on every push.** `tests/real_qgis_e2e.py` measures the largest
  system prompt, the largest tool schema list and the smallest request
  (`base_chars`), in characters, against the `scripted` section. The numbers
  are saved as `request_sizes.json` in the `e2e-screens-*` artifact.
- **Live, by hand and before a release.** `tests/real_qgis_live.py` records
  prompt, completion and total tokens and the request count of each scenario
  in `live_usage.json` (the `live-token-usage` artifact) and compares them
  with the `live` section. Ceilings belong to the model they were measured
  on; with another model the run only reports. The workflow sets
  `LIVE_REQUIRE_CEILINGS=1`, so there a scenario without a ceiling fails.

Refresh the ceilings only when spending changed on purpose, and say why in the
commit. Build live ceilings from two or three runs of the `live-model`
workflow; the script takes the largest value of each metric and adds headroom
(30 % live, 10 % scripted).

```bash
gh run download <run-id> -n live-token-usage -D /tmp/live-1
python3 tests/token_ceilings.py /tmp/live-1/live_usage.json /tmp/live-2/live_usage.json
```

Scripted ceilings come from one run of the scripted scenarios:

```bash
E2E_ARTIFACTS=/tmp/e2e QT_QPA_PLATFORM=offscreen python3 tests/real_qgis_workflows.py real_qgis_e2e
python3 tests/token_ceilings.py /tmp/e2e/request_sizes.json
```

Review the diff before committing: a ceiling that jumps is the regression this
check exists to catch.

## Manual checks

These need a real provider, a real network service or a person's eye.

1. **Providers.** Test connection and one run with tool calls on OpenAI,
   Anthropic (format `auto` sends to `/messages`), OpenRouter, Google Gemini
   and Ollama at `http://localhost:11434/v1` with an empty key. A remote
   address without a key says the key is missing.
2. **Reasoning.** A local reasoning model (a DeepSeek-R1 distill, QwQ) keeps
   its reasoning in the folded *Thought* line, not in the answer. Anthropic
   with a thinking budget of 4096 finishes a run with tools. DeepSeek with
   Reasoning on answers two tool-using questions in one conversation without
   a 400 about `reasoning_content`.
3. **Russian QGIS.** Switch the QGIS interface to Russian and restart. The
   panel, the settings and the plan card are in Russian, with the right plural
   forms for 1, 2 and 5 steps. German falls back to English. The agent answers
   in the language you write in.
4. **Themes.** In a light and a dark QGIS, and with the *Light* panel theme in
   a dark QGIS, the panel, the settings, the `@` and `/` lists, the menus and
   the cards are readable. Icons are sharp on a high-DPI screen.
5. **Motion.** The compass swings while the agent works and settles when it
   is done. Activity lists and *Thought* fold smoothly, also when clicked many
   times in a row.
6. **OpenStreetMap.** *Download the cafes in Tver* adds a point layer. A view
   wider than five degrees is refused before anything is sent.
7. **Open data.** A Sentinel-2 search asks for consent naming the Planetary
   Computer and lists scenes; loading one adds a raster. *Add the regions of
   Kenya* adds 47 regions. A connector switched off in Settings is refused.
8. **Web tools.** Search, page reading and geocoding each ask first. Saving
   `https://nominatim.openstreetmap.org` as your own geocoder is refused.
9. **Other plugins.** With qgis2web installed, starting its export asks a
   destructive confirmation and opens its window. Installing a plugin from
   the repository asks twice, and the plugin then shows in the Plugin Manager
   and its algorithms in the Processing Toolbox.
10. **A long step.** A buffer on a layer with tens of thousands of features:
    the map pans while it runs, the step shows its progress, ■ cancels it and
    the steps after it.
11. **Restart.** After a QGIS restart the conversation comes back with its
    activity lists and plan cards, and a follow-up question still uses the
    earlier context. Project notes stay with their project.
12. **Unloading.** Reloading the plugin during a request does not crash QGIS.
13. **Run journal.** Switch on *Run journal* in Settings → Privacy and apply a
    plan. The chat shows a path under `ai_agent_runs`; the folder has mode
    `0700` and the file `0600`.
14. **Print layout.** *Make an A4 layout with the map, a title, a legend and a
    scale bar, and export it to PDF*: the PDF opens, and on a vision model the
    check after Apply looks at the rendered layout.
15. **History.** *Keep conversations* set to 7 days removes older
    conversations but not the open one. *Delete history and journals* asks
    first, then empties both.
