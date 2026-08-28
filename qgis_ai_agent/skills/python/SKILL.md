---
name: python
description: Run a PyQGIS snippet when no dedicated tool covers the request — the escape hatch to the full QGIS API. Load this only after checking that a real tool cannot do the job.
tools: [run_python]
---

# The escape hatch

`run_python` executes Python inside the running QGIS. It reaches the whole
API, which is exactly why it is the **last** thing to reach for.

## Try a real tool first

Before loading this skill, check that the job truly has no tool. The other
domains cover reading the project, styling, processing, OSM, layouts, editing
data and managing layers. A snippet that re-implements `set_symbol` or
`query_layer` is a worse version of it: no validation, no readable plan step,
and the user has to read code instead of a sentence.

Reach for `run_python` when:

- the request needs a QGIS property no tool exposes (blend modes, custom
  renderer internals, provider-specific settings);
- a Processing algorithm needs wiring the `run_processing` schema cannot
  express;
- you are reading something exotic to answer a question.

## What the user sees

This tool is destructive-class: the code lands in the plan card and QGIS shows
the user a second dialog with the snippet itself before anything runs. So:

- **keep it short.** Ten readable lines beat forty clever ones. A person is
  going to read this.
- **`intent` is mandatory** and is written for that person, not for you: one
  plain sentence saying what the snippet does.
- **no surprises.** A snippet whose `intent` says "read the CRS" must not also
  delete a layer. Split unrelated work into separate calls.

## Writing the snippet

Ready-made names: `project` (`QgsProject.instance()`), `iface`, `processing`,
and the `Qgs*` / Qt classes — no imports needed for those.

`print()` is how you report back: the return value is not captured, and the
output comes to you as `output`. Print what you checked, not just "done".

Errors come back with the traceback — fix the snippet and queue a corrected
one instead of asking the user what went wrong. An endless loop is stopped by
a line budget; if you hit it, the loop is the bug.

## After it works

A snippet that solved a real task is a missing tool. Say so to the user in
plain words — "this worked, but it would be better as a proper tool" — so the
gap gets closed instead of being papered over with code every time.
