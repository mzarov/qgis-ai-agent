---
name: style
description: Inspect how a layer is drawn — renderer type, classification field, classes with colours, labels, opacity. Load this for questions about appearance, colours or labelling.
tools: [describe_style, describe_style_options, set_symbol, set_categories, set_graduated, set_labels, set_opacity, set_raster_style]
---

# Layer appearance

`list_layers` and `describe_layer` in the `inspect` skill return a one-line
`style_summary` per layer, such as "categories on field 'type', classes: 5". That
summary names the renderer and nothing else — **it never contains a colour**.
Those tools say so themselves, in `style_note`.

So split the question by what it asks for:

- *"how are the layers coloured?"*, *"which ones use categories, which a single
  symbol?"* — one `list_layers` call answers it; this skill is not needed.
- **Anything naming colours, class boundaries, labels or opacity — `describe_style`,
  once per layer in question.** There is no shortcut. A layer called "Rivers" does
  not tell you it is blue: answering "usually blue" is inventing the user's data,
  and "single symbol" is not an answer to "what colour".

## What you get

`describe_style` returns the renderer and, depending on its type:

| Renderer | Key fields |
|---|---|
| `singleSymbol` | one `symbol` with colour, size or width |
| `categorizedSymbol` | `class_attribute` plus `classes` with `value`, `label`, `symbol` |
| `graduatedSymbol` | `class_attribute` plus `classes` with `min`, `max`, `label`, `symbol` |
| `RuleRenderer` | `rules` with `filter` expression and `label` |

Each `symbol` carries `kind` (point / line / polygon), `color` and, for a
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

Name the mechanism, not just the colour. "The cities are red" is less useful than
"the layer is categorised on field `type`, and the `city` category is painted #e31a1c".

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
applies the batch. Say "I will recolour", not "I recoloured".

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

- the halo that makes labels readable over a busy map — "label outline", "halo",
  "so they stay readable" — is `buffer_color` and `buffer_size`, **not** `color`,
  which paints the glyphs themselves
- "move the labels" is `offset_x` / `offset_y` in millimetres, while "further from
  the marker" is `distance`; on `offset_y` a **negative** number moves labels up
- "dashed roads" is `stroke_style: "dash"` on `set_symbol`, and "no fill, outline
  only" is `fill_style: "none"`

Set everything in one call. "Label them with the name, bold, 12, white halo" is
one call with four keys, not four calls. Queueing either tool twice for one layer
means the second call wins outright and the first was wasted — both rebuild the
whole configuration each time rather than patching it.

Not every symbol property fits every geometry: `shape` is meaningless for lines,
`fill_style` for points. Such keys come back in `skipped` with a note. That is a
report, not a failure — the rest was applied, so do not retry the call.

### Rasters

The tools above are for vector layers. A raster gets `set_raster_style`:

| Ask | mode |
|---|---|
| colour the values with a ramp, "paint the DEM" | `pseudocolor` |
| plain grayscale stretch | `gray` |
| shaded relief, "make it look 3D", "hillshade" | `hillshade` |

`pseudocolor` reads the real min and max off the band, so the ramp always
covers the actual data — do not invent boundaries. `classes` and
`interpolation` (`linear`, `discrete`, `exact`) shape the transition; discrete
suits classified data, linear suits continuous elevation.

`hillshade` expects an elevation band; `azimuth` and `altitude` are the light
direction in degrees, and the defaults (315/45) are the cartographic
convention — change them only when asked.

`no_data_values` hides values as transparent on any mode. The classic case is
a `-9999` filler making the whole ramp useless: hiding it fixes the colours
without touching the data.

### Three different opacities

QGIS has three, and they are not interchangeable:

| What the user means | Where it lives |
|---|---|
| the whole layer see-through, rasters included | `set_opacity` |
| a see-through fill but a solid outline | `opacity` in `set_symbol` |
| see-through label text | `opacity` in `set_labels` |

"Make the layer see-through" is `set_opacity`. Reach for the other two only when
the user singles out the fill or the text.

### Reading before writing

For "why does it look like this" or "change this but leave the rest", call
`describe_style` first. Without it you do not know what you are replacing, and
these tools replace rather than patch.
