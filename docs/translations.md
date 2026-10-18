# Translations

All source text is English. Russian is a translation catalogue next to the
code. The plugin follows the QGIS interface language and falls back to English.

## Files

- Python code with `tr("Apply")`: the English original, which is also the key.
- `ai_agent/translations/ai_agent_ru.ts`: the catalogue. Edit only the
  translations.
- `ai_agent/translations/ai_agent_ru.qm`: the compiled file QGIS loads. Never
  edit it by hand.

A missing translation is harmless: `tr()` returns the English text.

## Updating

After adding or changing a `tr()` string:

```bash
python3 tools/update_translations.py
```

It needs no dependencies. It extracts `tr()` and `tr_n()` literals by parsing
the AST, adds new entries to the `.ts` (existing translations stay) and
compiles the `.qm` with `tools/qm.py`. Fill in the empty `<translation>`
entries and run it again.

The stock QGIS tools are not used:

- `pylupdate5` reads non-ASCII source as latin-1, misses `tr_n` and writes the
  wrong context.
- `lrelease` ships only with the Qt tools, which neither QGIS nor a typical
  system has. `tools/qm.py` produces byte-identical output, pinned by
  `tests/data/golden_ru.qm`, which `lrelease` built once.

`tests/test_i18n.py` fails when an entry is untranslated, a placeholder (`{0}`,
`%n`) is lost, or the catalogue drifts from the code.

## Rules

- `tr()` takes a literal: `tr("Layer '{0}'").format(name)`, never an f-string.
- Text a person reads (`summarize_call`, everything in `ui/`) goes through
  `tr()`. Text the model reads (tool descriptions, schemas, errors) stays plain
  English, so a Russian QGIS does not send the model Russian schemas.
- Plurals use `tr_n("%n step(s)", count)`; Russian has all three forms.

## Adding a language

1. Add the locale to `SUPPORTED_LOCALES` in `ai_agent/i18n.py` and to
   `LANGUAGE_NAMES` in `core/agent/prompts.py`.
2. Add its plural rules to `NUMERUS_RULES` in `tools/qm.py`. The compiler
   refuses unknown languages.
3. Add the language to `LANGUAGES` in `tools/update_translations.py`, run it
   and translate the new `.ts`.
