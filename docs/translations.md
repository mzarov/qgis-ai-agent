# Translations

The source language is English — all of it: code, tool schemas, prompts, UI
strings. Russian lives as a translation catalogue next to the code. The plugin
follows the QGIS interface language; unsupported locales fall back to English.

## How it works

Three files, of which you only ever edit the middle one:

| File | What it is | Edited by hand? |
| --- | --- | --- |
| `*.py` with `tr("Apply")` | the English original | yes — that is the code |
| `qgis_ai_agent/translations/qgis_ai_agent_ru.ts` | XML, English → Russian | yes, the translation column only |
| `qgis_ai_agent/translations/qgis_ai_agent_ru.qm` | the compiled binary QGIS loads | never — generated |

There is no separate key: the English string itself is the key. A missing
translation is harmless — `tr()` falls back to the English original.

## The workflow

After adding or changing a `tr()` string:

```bash
python3 tools/update_translations.py
```

The command needs no dependencies. It extracts the literals from `tr()` /
`tr_n()` by parsing the AST, appends new entries to the `.ts` (existing
translations survive), and compiles the `.qm` with our own compiler in
`tools/qm.py` — its output is byte-identical to Qt's `lrelease`, pinned by the
`tests/data/golden_ru.qm` fixture.

Then fill in the empty `<translation>` entries in the `.ts` and run the command
again. `tests/test_i18n.py` fails while anything is left untranslated, when a
placeholder (`{0}`, `%n`) is lost in translation, or when the catalogue drifts
from the code.

## Rules

- `tr()` takes a literal only: `tr("Layer '{0}'").format(name)` — never an
  f-string, which the extractor cannot read.
- User-facing text (`summarize_call`, everything in `ui/`) is wrapped in
  `tr()`. Model-facing text (tool descriptions, schemas, error messages) is
  plain English **without** `tr()` — piping it through the translator would
  send the model Russian schemas in a Russian QGIS.
- Plurals go through `tr_n("%n step(s)", count)`; Russian carries all three
  forms in the catalogue.

## Adding a language

1. Add the locale to `SUPPORTED_LOCALES` in `qgis_ai_agent/i18n.py` and to
   `LANGUAGE_NAMES` in `core/agent/prompts.py`.
2. Add its plural rules to `NUMERUS_RULES` in `tools/qm.py` — the compiler
   refuses unknown languages instead of guessing.
3. Add the language to `LANGUAGES` in `tools/update_translations.py`, run it,
   translate the generated `.ts`.
