---
name: inspect
description: Facts about the open project — layers, fields and their values, counts, lengths and areas via expressions, the user's selection, the current view, a rendered image of the map. Always loaded; read before you act.
tools: [get_project_info, list_layers, describe_layer, get_field_values, sample_features, query_layer, get_selection, select_features, get_canvas_extent, render_map, get_qgis_info]
---

# Reading the project

Start with `get_project_info` for anything broad about the project: it returns the
layer tree with groups and visibility, which `list_layers` does not.

## Before any analysis or styling

`describe_layer` gives three facts that silently break work if ignored:

- **`is_valid`** false — the source is missing. Tell the user instead of proceeding.
- **`subset_filter`** non-empty — counts and analysis cover only the filtered
  subset. Say so when it matters.
- **`crs_is_geographic`** true — layer coordinates are degrees, not metres.

Never classify or filter by a field before calling `get_field_values`: guessed
values produce plans that fail on real data. Its list is capped —
`unique_values_note` says when it was truncated; do not present it as complete.
`sample_features` shows real records when codes or abbreviations are ambiguous.

## Answering questions with numbers

"How many", "the largest", "average", "total", "top" are `query_layer` calls,
never guesses from a sample.

| Question | Call |
|---|---|
| How many motorways | `aggregate="count"`, `filter="highway = 'motorway'"` |
| Top 5 cities by population | `order_by="population DESC"`, `limit=5` |
| The longest river | `order_by="$length DESC"`, `limit=1`, `fields=["name"]` |
| Total lake area | `aggregate="sum"`, `expression="$area"` |
| Mean road length per type | `aggregate="mean"`, `expression="$length"`, `group_by="highway"` |

Length and area live in the geometry (`$length`, `$area`), not in a field — never
go looking for a length column.

- Field names are case-sensitive; string literals take single quotes:
  `highway = 'motorway'`.
- `$length` and `$area` follow the project: with an `ellipsoid` in
  `get_project_info` they come back in its `distance_units` / `area_units` —
  usually metres, even for a layer in degrees. With no ellipsoid they are raw CRS
  units, which on a geographic layer means degrees. Check once and state the unit.
- `aggregate="count"` counts features regardless of nulls; add
  `filter="field is not null"` to count values.

## The user's selection and the map

"Selected", "these", "highlighted" — call `get_selection` first, then pass
`selected_only=true` to `query_layer`. If nothing is selected, say so.

When the answer is *which* features rather than *how many*, `select_features`
shows them on the user's map — it changes no data.

`render_map` (with `layer_name` to frame one layer) is for how the map *looks*,
not for data questions. If it is not in your tool list, this model cannot see
images: judge the look from `describe_style` and the data, and never claim you
saw the map.

## Layer sources

`source` has credentials stripped (`password=<hidden>`). Never ask the user for a
password or put one into a tool call.

## "Why don't I see my layer?"

Check in this order and stop at the first hit: `describe_layer` → `is_valid`
false; `get_project_info` → the layer or its group is unchecked;
`describe_style` → opacity 0 or a `subset_filter` that matches nothing;
the extent is far from the view (`zoom_to_layer` in the project skill);
scale-dependent visibility, which only `run_python` can read
(`layer.hasScaleBasedVisibility()`).
