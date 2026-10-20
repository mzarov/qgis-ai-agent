# Skill evals

Two benches measure the agent against a real model. They run on
[promptfoo](https://www.promptfoo.dev/) with any OpenAI-compatible endpoint
and need Node for `npx`. The plugin and its tests do not need them.

- The **skill bench** checks single decisions: does the model load the right
  skills, and then call the right tool with the right arguments?
- The **agent bench** runs whole requests in a headless QGIS and checks what
  they leave in the project.

## The skill bench

Each case is one model request, built by the plugin's own
`core/agent/request.py` (`evals/context.py`): the system prompt, the tool
schemas after the skill under test is loaded, the project context and the
user's request. The project is described by `evals/fixture.json`. A change to a
`SKILL.md` or a tool description is measured on the next run.

A model that reads first is not marked down for it. When a turn holds only
reads the fixture can answer (`describe_layer`, `get_field_values` for any
field, `describe_processing`, `describe_style`, `list_layers`,
`get_project_info`, `get_canvas_extent`, `get_qgis_info`, `list_plugins`),
`evals/provider.py` answers them and asks again, up to three times. The
answers have the real tools' shape, taken from a headless QGIS run on a
project built to match the fixture, without layer ids. The case is judged on
every call made, so a forbidden call still fails it wherever it appears.

Suites:

- **routing** (`evals/routing.yaml`): the first turn, with only `inspect`
  loaded. Which skills does the model load?
- **one suite per skill** (`ai_agent/skills/<skill>/evals/cases.yaml`): the
  skill is loaded, and the case checks the next call. The cases never reach
  the plugin ZIP.

### A case

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
- `reads`: calls the agent already made, comma-separated: `roads` is
  `describe_layer`, `roads/highway` that field's values, `native:buffer` the
  algorithm's description. A read with its own result goes under
  `{steps: [{tool, args, result}]}`. Do not use a YAML list here: promptfoo
  turns a list in `vars` into one test per item.
- `expect`: `call` and `args`, `loads` and `not_loads`, `not` (tools it must
  not call), `after` (`{run_processing: describe_processing}`: a run only
  once described), `answer` (a reply without a tool call) and `any_of`.
  `evals/checks.py` documents every key.

Matching is lenient: strings ignore case, `"500"` equals `500`, a dict matches
on its listed keys, `re:` starts a regular expression, `*` only requires the
argument, and `"~33580±1%"` is a number within 1 %.

### Running it

```bash
export EVAL_API_URL=https://api.deepseek.com/v1
export EVAL_MODEL=deepseek-chat
export EVAL_API_KEY=...   # not needed for a local server
python3 evals/run.py
```

- `--suites routing,style` runs only those suites; `--only "Labels|Buffer"`
  only matching cases.
- `--repeat 3 --fresh` runs each case three times without the cache and
  reports the pass rate.
- Several comma-separated models in `EVAL_MODEL` are compared side by side.
- `EVAL_LOCALE=ru` builds the prompt for the Russian interface.
- `EVAL_AUTH=OAuth` is for gateways that want OAuth instead of Bearer.

The runner prints passed cases, tokens and latency per suite, with each
failure and what the model did instead. The same table goes to
`build/evals/summary.md`; `npx promptfoo view` shows the cases one by one.

## The agent bench

```bash
python3 evals/run.py --agent
```

- `evals/agent/fixture.py` builds a small city as real layers in UTM 37N, with
  fixed values, so a task can name its exact outcome.
- `evals/agent/tasks.yaml` holds the tasks: styles, buffers, fields, edits,
  exports, a layout, joins, a chart, a chain across skills.
- `evals/agent/server.py` runs inside QGIS. For each task it builds the
  project, sends the request, presses Apply for every batch (destructive steps
  included), waits for the check after Apply and returns the answer, the tools
  that ran, tokens and a snapshot of the project.
- `evals/agent/outcome.py` compares the snapshot with the task's `expect`:
  the answer, layers, written files and the project. Areas are measured on the
  ellipsoid, so a buffer drawn in Web Mercator "metres" fails.

On macOS with QGIS 4 installed the server runs in that QGIS's Python;
elsewhere, or with `--agent-server docker`, in the pinned QGIS image. The log
goes to `build/evals/agent-server.log` and the results to
`build/evals/agent.results.json`. `tests/real_qgis_agent_bench.py` checks the
server's plumbing against the scripted model on every CI run.

## In CI

The `skill-evals` workflow never runs on push. Start it from the Actions tab
(optionally with suites, a repeat count, `save_thresholds` or `agent`), or put
the `skill-evals` label on a pull request. It uses the live-model provider
settings: `LIVE_MODEL_URL`, `LIVE_MODEL`, the `LIVE_MODEL_KEY` secret and
`LIVE_MODEL_AUTH`. Pull requests from forks get no secrets and are skipped.

Each suite has a floor in `evals/thresholds.json`: a baseline pass rate less
ten points, rounded down to five. A run fails only below a floor. Floors belong
to the model they were measured on. To set them, run the workflow with
`repeat` 3 and `save_thresholds`, or locally
`python3 evals/run.py --repeat 3 --fresh --save-thresholds`, and commit the
file. `EVAL_REQUIRE_THRESHOLDS=1` fails a suite without a floor.

## When to run it

- After editing a `SKILL.md`, a tool description or the prompt core: that
  skill's suite, plus routing when a skill description changed.
- After changing a tool's behaviour, Apply or verification: the agent bench.
- Before a release: everything, with `--repeat 3 --fresh`.
- With a new skill: add `evals/cases.yaml` next to its `SKILL.md` (the
  requests it exists for, a pitfall its rules warn about, one request in
  Russian) and a routing case.

`tests/test_skill_evals.py` checks that every tool and skill a case names
exists and that requests are built by the plugin's code.
