---
name: style
description: Inspect how a layer is drawn — renderer type, classification field, classes with colours, labels, opacity. Load this for questions about appearance, colours or labelling.
tools: [describe_style, describe_style_options, set_symbol, set_categories, set_graduated, set_labels, set_opacity]
---

# Layer appearance

`list_layers` and `describe_layer` in the `inspect` skill return a one-line
`style_summary` per layer, such as "категории по полю «type», классов: 5". That
summary names the renderer and nothing else — **it never contains a colour**.
Those tools say so themselves, in `style_note`.

So split the question by what it asks for:

- *"каким способом раскрашены слои?"*, *"где категории, где одиночный символ?"* —
  one `list_layers` call answers it; this skill is not needed.
- **Anything naming colours, class boundaries, labels or opacity — `describe_style`,
  once per layer in question.** There is no shortcut. A layer called «Реки» does
  not tell you it is blue: answering "обычно синий" is inventing the user's data,
  and "одиночный символ" is not an answer to "какого цвета".

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

## Changing how a layer looks

Five write tools. Each **replaces** the renderer, so pick the one that matches the
question rather than stacking calls on the same layer:

| Ask | Tool |
|---|---|
| how the layer itself is drawn | `set_symbol` |
| a colour per value of a text field | `set_categories` |
| classes over a numeric field | `set_graduated` |
| turn labels on or off | `set_labels` |
| make a layer see-through | `set_opacity` |

`set_labels` and `set_opacity` are additive — they leave the renderer alone. The
other three overwrite it, so applying `set_categories` after `set_symbol` on the
same layer makes the first call pointless. Queue only the call you actually mean.

These are write tools: the call returns `{"status": "queued"}` and the user
applies the batch. Say "перекрашу", not "перекрасил".

### Choosing between categories and graduations

Text field with a handful of distinct values — `set_categories`. Numeric field
with a continuous spread — `set_graduated`. If you do not know which, call
`get_field_values` from the `inspect` skill first: it shows both the type and how
many distinct values there are. Categorising a field with hundreds of values
produces an unreadable map, and the tool refuses past 60.

### Colours and ramps

Colours are `#rrggbb` or English colour names. A ramp name must exist in the user's
QGIS style library, and that library varies per install — do not trust a name you
merely remember. Omitting `ramp` is safe: the tool picks a sensible default. Naming
one that does not exist is also safe: the error lists what is available and you
pick from that list. Common built-ins are `Spectral`, `Viridis`, `Blues`, `Set2`.

Pick a ramp that suits the data: sequential (`Blues`, `Viridis`) for magnitudes,
diverging (`Spectral`, `RdYlGn`) when there is a meaningful middle, qualitative
(`Set2`, `Paired`) for categories that have no order.

### Two tools take a property bag

`set_symbol` and `set_labels` both take `layer_name` plus a single `properties`
object. Everything about the thing lives there — for a symbol: colour, opacity,
size, stroke colour and width, dash pattern, marker shape, fill hatching; for a
label: field, font, weight, size, colour, the halo around the glyphs, offsets,
rotation, placement, shadow, background.

**`describe_style_options` is the source of truth** for what those keys are called,
what values they take and in what units. Pass `kind: "symbol"` or `kind: "labels"`.
It is generated from the same catalogue the tools apply, so it cannot drift from
what actually works. Call it when you are not certain of a key — guessing produces
an error listing near matches, which costs a round trip.

Three keys are worth naming here because users describe them in words that do not
match the key:

- the halo that makes labels readable over a busy map — "обводка подписей", "ореол",
  "чтобы читались" — is `buffer_color` and `buffer_size`, **not** `color`, which
  paints the glyphs themselves
- "сдвинь подписи" is `offset_x` / `offset_y` in millimetres, while "подальше от
  значка" is `distance`; on `offset_y` a **negative** number moves labels up
- "пунктирные дороги" is `stroke_style: "dash"` on `set_symbol`, and "без заливки,
  только контур" is `fill_style: "none"`

Set everything in one call. "Подпиши названиями, жирным, 12, с белой обводкой" is
one call with four keys, not four calls. Queueing either tool twice for one layer
means the second call wins outright and the first was wasted — both rebuild the
whole configuration each time rather than patching it.

Not every symbol property fits every geometry: `shape` is meaningless for lines,
`fill_style` for points. Such keys come back in `skipped` with a note. That is a
report, not a failure — the rest was applied, so do not retry the call.

### Reading before writing

For "почему это выглядит так" or "поменяй, но остальное оставь", call
`describe_style` first. Without it you do not know what you are replacing, and
these tools replace rather than patch.
