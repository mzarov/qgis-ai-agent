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
- `*` only asks for the argument to be present.

## Running it

You need Node, for `npx`. The plugin and its tests need nothing.

```bash
export EVAL_API_URL=https://api.deepseek.com/v1
export EVAL_MODEL=deepseek-chat
export EVAL_API_KEY=...   # not needed for a local server
export EVAL_AUTH=OAuth    # only for a gateway that wants OAuth instead of Bearer
python3 evals/run.py
```

- `--suites routing,style` runs only those suites.
- `--repeat 3` runs every case three times and reports the pass rate.
- Several comma-separated models in `EVAL_MODEL` are compared side by side.
- `EVAL_LOCALE=ru` builds the prompt as for the Russian interface.

The runner writes a promptfoo config per suite to `build/evals/`. It runs
them, then prints a table of passed cases, tokens and latency per suite, with
every failure and what the model did instead. The same table goes to
`build/evals/summary.md`. To see the cases one by one, run `npx promptfoo
view`. Telemetry, update checks and sharing are switched off for the run.

## When to run it

- After editing a `SKILL.md`, a tool description or the prompt core: run that
  skill's suite, and the routing suite when a skill description changed.
- Before a release: run everything, with `--repeat 3` for the cases that
  wobble.
- With a new skill: add `evals/cases.yaml` next to its `SKILL.md`. Cover the
  requests it exists for, a pitfall its rules warn about, and one request in
  Russian. Add a routing case for it.

`tests/test_skill_evals.py` guards the bench itself:
- every tool a case names exists in its skill;
- every skill a case expects exists;
- the request is built by the plugin's code;
- the check reads tool calls in every shape promptfoo returns.
