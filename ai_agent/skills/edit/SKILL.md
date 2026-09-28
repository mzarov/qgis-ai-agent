---
name: edit
description: Change or delete existing records in place — set attribute values, remove features; writes to the data source. Load this when the data itself must be corrected, not restyled, analysed or restructured.
tools: [update_attributes, delete_features]
---

# Editing data in place

These tools change the user's actual data — files on disk, tables in a
database. They are marked destructive: on top of the usual plan card the plugin
asks the user one more time, listing exactly these steps. That second prompt is
the plugin's job; yours is to make the steps precise and small.

## Read before you touch

Editing blind is how data gets ruined. Before queueing:

- confirm the field and its values with `get_field_values` or `query_layer` —
  the filter you write must match what is really in the data;
- if the request points at the screen (“these”, “the selected ones”), read
  `get_selection` first and turn it into a filter the user can see, such as
  `id in (…)` or the attribute the selection shares.

`prepare` re-counts the matches at queue time and refuses a filter that matches
nothing — that usually means a typo in a value, not an empty layer.

## update_attributes

Sets fields to **constant** values on every feature matching the filter:
`{"type": "park"}`. It does not evaluate expressions — for a computed value
(`upper(name)`, `$area`) use `native:fieldcalculator` from the processing
skill, which writes a new layer instead of touching the source.

All fields go in one call. Without a filter it touches every feature — pass one
whenever the request allows.

## delete_features

The filter is mandatory. Deleting everything requires the literal filter
`all` — an explicit word, never a default. More than 10000 matches are refused:
a wipe that size should be a conscious manual act, not a chat message.

## Honesty about scope

Edits are committed straight to the provider, so there is no undo button
afterwards. Say what was changed in numbers — the tools return `updated` and
`deleted` counts, and the verification pass can re-read the data to prove the
result. Geometry editing is not supported yet: say so instead of improvising
through processing algorithms.

## Scratch layers

Edits to a scratch layer (its `source` starts with `memory`) live only until QGIS
closes. Say so when you edit one, and suggest `export_layer` from the project
skill if the user wants to keep the result.
