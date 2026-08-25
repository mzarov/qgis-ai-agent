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

Each `symbol` carries `kind` (точки / линии / полигоны), `color` and, for a
single-layer symbol with an outline, `stroke_color` and `stroke_width`. Colours
are hex strings (`#e31a1c`). Class lists are capped at 30 entries.

## Symbols built from several layers

When `layers` is present, the symbol is stacked: layer 0 draws first, later
layers draw on top. **Read the whole stack before describing the appearance** —
the top-level `color` is only the symbol's nominal colour and often is not what
dominates the picture.

The common road casing looks like this:

```
layers: [{index: 0, color: "#000000", width: 1.4},
         {index: 1, color: "#ff6011", width: 0.8}]
```

That is an orange line over a wider black one, so the road reads as orange with
a black border. Describing only layer 0 would call the road black; describing
only the top-level colour would miss the border entirely.

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
