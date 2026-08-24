---
name: inspect
description: Read the current QGIS project — structure, layers, attribute data, CRS, environment. Load this whenever you need facts about the project before answering or acting.
tools: [get_project_info, list_layers, describe_layer, get_field_values, sample_features, get_canvas_extent, get_qgis_info]
---

# Reading the project

These tools only read. They never modify anything, so use them freely and without
asking the user for permission.

## Choosing a tool

| Question | Tool |
|---|---|
| What is this project? Groups, visibility, units, themes | `get_project_info` |
| Which layers exist? | `list_layers` |
| What is in this layer? Fields, extent, CRS, source, style | `describe_layer` |
| What values does this field hold? | `get_field_values` |
| What does the actual data look like? | `sample_features` |
| What is currently on screen? | `get_canvas_extent` |
| Which QGIS version and providers are available? | `get_qgis_info` |

Start with `get_project_info` when the user asks anything broad about their
project — it returns the layer tree with groups and visibility, which `list_layers`
does not.

## Before any analysis or styling

`describe_layer` gives you three things that silently break work if ignored:

- **`is_valid`** — false means the source is missing or the path is broken.
  Nothing will work on that layer; tell the user instead of proceeding.
- **`subset_filter`** — a non-empty filter means `feature_count` and any analysis
  cover only the filtered subset, not the whole layer. Say so when it matters.
- **`crs_is_geographic`** — true means distances are in degrees, not metres.

Never classify or filter by a field before calling `get_field_values`. Guessing
which values a field holds produces plans that fail on real data.

## Reading data

- `get_field_values` returns unique values, and for numeric fields also min and max.
  This is what you need to choose class boundaries or write a filter expression.
- `sample_features` shows real records. Reach for it when field names alone are
  ambiguous — codes, abbreviations, mixed-language values.
- Both are capped. `unique_values_note` tells you when the list was truncated;
  do not present a truncated list as complete.

## Layer sources

`source` has credentials stripped: `password=‹скрыто›`. Never ask the user for a
password, and never suggest putting one into a tool call.

## Cost

Reading is cheap but not free. Call each tool once per task and remember the
result — do not re-read the same layer between steps of the same plan.
