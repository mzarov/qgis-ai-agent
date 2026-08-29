# qgis_tools/ — the agent's hands

All PyQGIS execution logic. One tool — one class — one file, around 200 lines.

## The tool contract

```python
class DescribeLayerTool(BaseTool):
    name = "describe_layer"            # snake_case, unique in the registry
    description = "..."                # English, goes into the schema for the model
    skill = "inspect"                  # domain: which skill loads this tool
    safety = SAFETY_READ               # read | write | destructive
    constraints = ["The layer must exist"]
    examples = ["Which fields does the roads layer have?"]
    params_schema = [
        {"name": "layer_name", "type": "string", "description": "...", "required": True},
    ]

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        ...

    def summarize_call(self, params: dict[str, Any]) -> str:
        ...

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        ...
```

`get_openai_schema()` is built from `params_schema` automatically — never write
the schema by hand. Supported `type`s: `string`, `number`, `integer`, `boolean`,
`array`, `object`; the optional `enum` lists the allowed values.

## Rules

1. **`skill` and `safety` are mandatory.** Without `skill` the tool lands in no
   set. The `safety` default is `write` — a reading tool sets `SAFETY_READ`
   explicitly.
2. **`read` has no right to change anything.** It runs without the user's
   confirmation. Any mutation of the project is `write`, however harmless.
3. **`summarize_call` has no right to crash.** The loop calls it on the error
   path too: if it throws on malformed arguments, error handling itself breaks,
   not just one line in the feed. Wrap anything that may fail to parse in `try`
   and fall back to a generic word. `tests/test_tools.py` catches this.
4. **`summarize_call` is the only thing here a person sees.** So only it gets
   wrapped in `tr()`, and only it may carry a literal for translation:
   `tr("Reading layer '{0}'.").format(name)`. The knowledge of what a step
   looks like lives in the tool, not in the registry. Show coordinates the user
   did not give as “auto” — never substitute invented defaults.
5. **Errors carry clear English text and a hint, without `tr()`.** The model
   reads them and corrects itself. When an object is missing, attach the list
   of available ones (see `common/layers.py::find_layer_by_name`).
6. **Shared code lives in `common/`, not in a neighbouring domain.** There:
   `layers.py` — layer lookup, CRS, extents; `values.py` — value coercion,
   limits, name hints; `layer_meta.py` — source, validity, opacity;
   `renderers.py` — renderer type and one-line summary. Domains never import
   each other: the urge to import from a sibling domain means the shared place
   for that code is `common/`.
7. **Results must serialise to JSON.** Return PyQGIS objects as names or
   identifiers (see `processing/utils.py::normalize_output`).
8. **Registration:** class → the domain list in `<domain>/__init__.py` → the
   list import in `registry.py`. Plus `skills/<domain>/SKILL.md` with the same
   tool name in `tools`.
9. **A new tool means a new test.** The contract and the schema are checked
   automatically for every tool, but `execute` logic needs its own coverage: on
   fake PyQGIS objects, as in `tests/test_renderers.py`. Both `describe_style`
   failures survived to live QGIS precisely because nobody called that code.

## PyQGIS — do not hallucinate

1. The target is QGIS 4.0. The QGIS 2.x API does not exist (no
   `QgsComposition`).
2. Project state — always through `QgsProject.instance()`.
3. Processing: `QgsApplication.processingRegistry()`, the `processing` module.
4. `try/except` around anything risky, log through
   `QgsMessageLog.logMessage(msg, "AI Agent", Qgis.Info)`.
5. Imports at the top, absolute. Code without comments or docstrings — see the
   root CLAUDE.md.

## Domain boundaries

`inspect/`, `project/`, `style/`, `processing/` depend only on `base.py` and
`common/`. Inside a domain the shared code has its own file: for `style/` it is
`apply.py` (ramps, repaint), for `project/` it is `tree.py` (layer tree and
groups). There must be no dependencies between the domains themselves —
otherwise deleting one would require edits in another, and the promise “a new
domain is only new files” would stop being true.

## When a domain is boundless

When a domain holds hundreds of operations (like Processing algorithms), do not
write a class per operation. Give three tools — search, signature description,
run — and describe how to use them in `SKILL.md`. The model: `processing/`.

## When an object has dozens of properties

A parameter per property does not scale: `QgsPalLayerSettings` has 111 members,
`QgsTextFormat` has 27 setters. Instead — a property bag: one `properties`
parameter of type `object` plus a catalogue in code and a reading tool that
serves it.

The machinery is shared and lives in `common/properties.py` — `StyleProperty`
and `PropertySet` with value coercion, range checks, typo hints and the parsing
of the `properties` parameter. Catalogues belong to the domains: `style/` keeps
`label_catalogue.py` and `symbol_catalogue.py`, `project/` keeps
`catalogues.py`. The machinery moved up into `common/` when a second domain
needed it — not earlier.

The catalogue must be the single source of truth. The describing tool is built
from it too, so it cannot drift from the implementation — unlike a property
list hand-copied into `SKILL.md`. Adding a property = one catalogue entry;
no new tool, no schema edit, no skill edit.

**Coercion must validate the value in `coerce`, not at execution.** A write tool
executes after the loop has ended, and there is nobody left to return an error
to. Exactly that broke when the machinery was extracted: the colour was checked
in `native()` at execution time, and an invalid colour silently rode all the way
to being applied.

A property inapplicable to the layer's geometry (marker shape on lines) must not
vanish silently: it comes back in `skipped` with a note that this is a report,
not a refusal.
