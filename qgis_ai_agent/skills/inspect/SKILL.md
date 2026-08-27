---
name: inspect
description: Read the current QGIS project — structure, layers, attribute data, CRS, environment. Load this whenever you need facts about the project before answering or acting.
tools: [get_project_info, list_layers, describe_layer, get_field_values, sample_features, query_layer, get_canvas_extent, get_qgis_info]
---

# Reading the project

These tools only read. They never modify anything, so use them freely and without
asking the user for permission.

## Choosing a tool

| Question | Tool |
|---|---|
| What is this project? Groups, visibility, units, themes | `get_project_info` |
| Which layers exist? | `list_layers` |
| What is in this layer? Fields, extent, CRS, source | `describe_layer` |
| What values does this field hold? | `get_field_values` |
| What does the actual data look like? | `sample_features` |
| How many, which are the largest, what is the total? | `query_layer` |
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

## Answering questions with numbers

`query_layer` runs QGIS expressions over a layer. Any question that starts with
"how many", "which is the largest", "average", "total" or "top" is a `query_layer`
call, not a guess from `sample_features`.

| Question | Call |
|---|---|
| How many roads of type motorway | `aggregate="count"`, `filter="highway = 'motorway'"` |
| Top 5 cities by population | `order_by="population DESC"`, `limit=5` |
| The longest river | `order_by="$length DESC"`, `limit=1` |
| Total area of the lakes | `aggregate="sum"`, `expression="$area"` |
| Average road length per type | `aggregate="mean"`, `expression="$length"`, `group_by="highway"` |

### Length and area are not fields

Geometry is available through expressions — `$length`, `$area`, `$geometry`,
`intersects()`, `distance()`, `buffer()`.

**Never go looking for a field that holds length or area.** Layers almost never
have one, and failing to find it is not an answer. "Which river is the longest" is
a single call:

```
query_layer(layer_name="Rivers", order_by="$length DESC", limit=1, fields=["name"])
```

The same mistake wears other disguises: scanning `describe_layer` for a `length`
column, sampling features hoping to spot one, or telling the user the data is
missing. The data is in the geometry — measure it.

Rules that matter:

- Field names are case-sensitive and must match `describe_layer` exactly. String
  literals use **single quotes**: `highway = 'motorway'`. Without them QGIS reads
  the word as a column name — the tool now rejects that instead of returning zero
  matches, but write the quotes and save yourself the round trip.
- `$length` and `$area` follow the project. When `get_project_info` reports an
  `ellipsoid`, they are computed on it and returned in `distance_units` /
  `area_units` — usually metres, even for a layer stored in degrees. With no
  ellipsoid set they are raw CRS units, and on a geographic layer that means
  degrees, which is meaningless. Check `get_project_info` before quoting a
  measured number, and state the unit you are quoting.
- `aggregate="count"` counts matched features regardless of nulls. To count
  non-empty values add `filter="field is not null"`.
- `order_by` works only without `aggregate`.
- If the tool reports that too many features match, add a `filter` — it refuses to
  return a partial aggregate rather than answer wrongly.

## Layer sources

`source` has credentials stripped: `password=<hidden>`. Never ask the user for a
password, and never suggest putting one into a tool call.

## Cost

Reading is cheap but not free. Call each tool once per task and remember the
result — do not re-read the same layer between steps of the same plan.
