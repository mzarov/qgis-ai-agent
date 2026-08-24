---
name: style
description: Inspect how a layer is drawn — renderer type, classification field, classes with colours, labels, opacity. Load this for questions about appearance, colours or labelling.
tools: [describe_style]
---

# Layer appearance

`describe_layer` in the `inspect` skill already returns a one-line `style_summary`
such as "категории по полю «type», классов: 5". Load this skill only when that
line is not enough — when the user asks about specific colours, class boundaries,
labels, or why a layer looks the way it does.

## What you get

`describe_style` returns the renderer and, depending on its type:

| Renderer | Key fields |
|---|---|
| `singleSymbol` | one `symbol` with colour, size or width |
| `categorizedSymbol` | `class_attribute` plus `classes` with `value`, `label`, `symbol` |
| `graduatedSymbol` | `class_attribute` plus `classes` with `min`, `max`, `label`, `symbol` |
| `RuleRenderer` | `rules` with `filter` expression and `label` |

Each `symbol` carries `kind` (точки / линии / полигоны), `fill_color` and, where
the symbol has an outline, `stroke_color` and `stroke_width`. Colours are hex
strings (`#e31a1c`). **The fill is not always what the user sees** — a white point
with a dark outline reads as dark, so mention the stroke when it carries the
visual weight.

When `symbol_layers` is present the symbol is built from several stacked layers
and only the first is described; say so rather than presenting it as the whole
picture. Class lists are capped at 30 entries.

`labeling` reports whether labels are on, which field or expression drives them,
font family, size and colour.

## Answering appearance questions

Name the mechanism, not just the colour. "Города красные" is less useful than
"слой категоризован по полю `type`, и категория `city` окрашена в #e31a1c".

When the classification field matters, cross-check it with `get_field_values`
from the `inspect` skill: a renderer can reference a field whose values have
since changed, leaving classes that match nothing.

## Limits

This skill is read-only. There are no tools to change styling yet, so do not
promise to recolour anything — describe what is there and, if the user wants a
change, say plainly that it is not supported yet.
