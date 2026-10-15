# Skill evals

The skill bench measures how well a model works with our skills: given a
request, does it load the right skills, and once a skill is loaded, does it
call the right tool with the right arguments? It runs on
[promptfoo](https://www.promptfoo.dev/) against any OpenAI-compatible
endpoint. Every case is one model request, so the full bench costs about a
million tokens and a few minutes.

The bench checks the model's decisions, not their effect in QGIS. A model can
pick the right tool, and the tool can still fail, or a chain can fall apart at
step five. Running the whole agent against a live project is the next stage
of the bench.

## What a case sends

Prompts and schemas are never copied into the bench. `evals/context.py`
builds each request with the plugin's own `core/agent/request.py`, exactly as
for a real turn:

- the system prompt, with the skill descriptions and the loaded skill's body;
- the tool schemas the model has once that skill is loaded;
- the per-turn state with the project context;
- the user's request, after a `load_skill` call for the skill under test and
  any reads the case lists.

The project is described by `evals/fixture.json`: layers `districts`,
`roads`, `schools`, `stations`, `dem` and `OpenStreetMap`, with their fields,
sample values and a few Processing algorithm descriptions. Edit a `SKILL.md`
or a tool description, and the next run measures the edit.

## Suites

- **routing** (`evals/routing.yaml`): the first turn, with only `inspect`
  loaded. Which skills does the model load for a request?
- **one suite per skill** (`ai_agent/skills/<skill>/evals/cases.yaml`): the
  skill is loaded, and the case checks the model's next call.

The cases live next to the skill's `SKILL.md`, so a new skill brings its cases
in the same folder. The build packs only `SKILL.md` and Python files from
`skills/`, so the cases never reach the plugin zip.

## A case

```yaml
- description: Graduated classes with a count
  vars:
    request: Colour the districts by population in 5 classes
    reads: districts
    expect:
      call: set_graduated
      args: {layer_name: districts, field: pop2020, classes: 5}
```

- `request`: what the user writes, in English or Russian.
- `reads`: calls the agent already made, separated by commas. `roads` is
  `describe_layer`, `roads/highway` is that field's values, and
  `native:buffer` is the algorithm's description, all taken from the fixture.
  A read with its own result goes under `{steps: [{tool, args, result}]}`.
  Never write a YAML list here: promptfoo turns a list in `vars` into one test
  per item.
- `measurements: none` describes the project without an ellipsoid, with the
  plugin's own `Measurements:` line. The fixture has one, as a new QGIS project
  does.
- `expect`: what counts as right. `evals/checks.py` explains every key:
  - `call` and `args`: the tool and the arguments it was called with;
  - `loads` and `not_loads`: the skills it loaded or must not load;
  - `not`: tools it must not call;
  - `answer`: it answered in words, without calling a tool;
  - `any_of`: any one of several expectations.

Matching is lenient, the way a person reads an answer:
- strings ignore case;
- `"500"` equals `500`;
- a dict matches when its listed keys do;
- `re:` starts a regular expression;
- `*` only asks for the argument to be present;
- `"~33580±1%"` is a number within 1 % of 33580, for measured sizes (1 % when
  the `±` part is left out).

## Running it

You need Node, for `npx`. The plugin and its tests need nothing.

```bash
export EVAL_API_URL=https://api.deepseek.com/v1
export EVAL_MODEL=deepseek-chat
export EVAL_API_KEY=...   # not needed for a local server
export EVAL_AUTH=OAuth    # only for a gateway that wants OAuth instead of Bearer
python3 evals/run.py
```

- `--suites routing,style` runs only those suites; `--only "Labels|Buffer"` only the cases whose description matches.
- `--repeat 3 --fresh` runs every case three times and reports the pass rate.
  promptfoo answers an unchanged request from its cache, so an untouched suite
  costs nothing on a rerun; `--fresh` asks the model again, which is what a
  pass rate needs.
- Several comma-separated models in `EVAL_MODEL` are compared side by side.
- `EVAL_LOCALE=ru` builds the prompt as for the Russian interface.

The runner writes a promptfoo config per suite to `build/evals/`. It runs
them, then prints a table of passed cases, tokens and latency per suite, with
every failure and what the model did instead. A case that never reached the
model (a timeout, a refused request) is counted apart, not as a failure. The same table goes to
`build/evals/summary.md`. To see the cases one by one, run `npx promptfoo
view`. Telemetry, update checks and sharing are switched off for the run.

## The agent bench

The skill bench checks one decision. The agent bench checks a whole request.
The plugin runs in a headless QGIS against a real model, with the real tools,
through Apply and the check after it. The bench then looks at what the request
left in the project, never at the route the model took.

- **The project** (`evals/agent/fixture.py`) is the city the skill bench
  describes, as real layers: 12 districts, 30 roads, 24 schools, 9 stations in
  UTM 37N, a DEM, and two CSV files. Every value is fixed, so a task can name
  its exact outcome: 3 schools hold fewer than 100 places, 5 hold more than
  1000, the districts hold 993 209 people.
- **The tasks** (`evals/agent/tasks.yaml`): styles, buffers, points in polygons,
  fields, edits, questions answered from the data, drawing, notes, exports, a
  print layout, joins, CSV points, the project CRS, a chart, and a chain across
  skills.
- **The provider** (`evals/agent/server.py`): promptfoo's HTTP provider posts
  each task to a server inside QGIS. The server builds the project in a fresh
  folder, opens the plugin in a main window with a map canvas, so the agent's
  look at the rendered map works as on the desktop, sends the request, presses
  Apply for every prepared batch (a
  destructive step is confirmed), waits for the check after Apply, and answers
  with the final answer, the tools that ran, tokens, requests, seconds and a
  snapshot of the project (`evals/agent/state.py`).
- **The check** (`evals/agent/outcome.py`) matches the snapshot against the task's
  `expect`. It looks at the answer, the state of existing layers, new layers,
  written files, the project and the tools that ran. A run that asks a
  question, leaves a batch unapplied or never reaches the model fails and says
  why. Checks name values, not only shapes: a polygon layer's area is measured
  on the ellipsoid whatever its CRS, so a buffer drawn in Web Mercator "metres"
  (0.56 m at Moscow's latitude) fails despite the right feature count.

```yaml
- description: A metric buffer on a layer in degrees
  vars:
    request: Make a 500 m buffer around the schools
    expect:
      new_layers: [{geometry: polygon, feature_count: 24, measured_km2: "~18.70±2%"}]
```

`{folder}` in a request is the task's own folder, for exports.

```bash
python3 evals/run.py --agent
```

The same `EVAL_*` variables apply. The runner starts the server, runs the
tasks one at a time and stops it; the server's log lands in
`build/evals/agent-server.log`. On macOS with QGIS 4 installed, the server runs
in that QGIS's own Python, at full speed and on the machine's own network, so a
model behind a VPN or on an internal IPv6-only address is reachable. Elsewhere,
or with `--agent-server docker`, it runs in the pinned QGIS image. A container
on macOS is emulated and does not see a VPN's names; there the key reaches the
container by name only. A run of all the tasks takes about a million tokens.
`--agent-url` points at a server that is already running.

`tests/real_qgis_agent_bench.py` runs the server's parts in live QGIS against
the scripted model on every CI run. It covers the fixture's numbers, Apply and
the snapshot, so the bench's plumbing cannot rot between real runs.

## In CI

The `skill-evals` workflow runs the bench on GitHub. It never runs on push,
because every run spends tokens. There are two ways to start it:

- from the Actions tab (**skill-evals → Run workflow**), optionally with a
  list of suites, a repeat count, or `save_thresholds`;
- by putting the `skill-evals` label on a pull request that touches a skill, a
  tool description or the prompt.

Tick `agent` on a manual run to add the agent bench; its suite has a floor like
the others.

It uses the same provider as the live-model workflow: the `LIVE_MODEL_URL` and
`LIVE_MODEL` variables, the `LIVE_MODEL_KEY` secret, and `LIVE_MODEL_AUTH` when
the gateway wants something other than Bearer. Pull requests from forks get no
secrets, so their run is skipped with a notice. Contributors run the bench
locally with their own key or a local model.

A model's answers vary, so CI does not demand every case. Each suite has a
floor in `evals/thresholds.json`: the pass rate of a baseline run less ten
points, rounded down to five. The run fails only when a suite drops below its
floor. Floors belong to the model they were measured on; with another model
the run just reports.

Setting the floors, once per model:

1. Run the workflow with `repeat` 3 and `save_thresholds` ticked, or locally
   `python3 evals/run.py --repeat 3 --fresh --save-thresholds`.
2. Take `evals/thresholds.json` from the `skill-evals` artifact and commit it.

Until then, `--check` only reports. `EVAL_REQUIRE_THRESHOLDS=1` makes a suite
or a model without a floor fail too. The table and the floors' verdict also go
to the run's summary page, and the raw results to the `skill-evals` artifact.

## When to run it

- After editing a `SKILL.md`, a tool description or the prompt core: run that
  skill's suite, and the routing suite when a skill description changed.
- Before a release: run everything, with `--repeat 3 --fresh` for the cases that
  wobble.
- With a new skill: add `evals/cases.yaml` next to its `SKILL.md`. Cover the
  requests it exists for, a pitfall its rules warn about, and one request in
  Russian. Add a routing case for it.

`tests/test_skill_evals.py` guards the bench itself:
- every tool a case names exists in its skill;
- every skill a case expects exists;
- the request is built by the plugin's code;
- the check reads tool calls in every shape promptfoo returns.
