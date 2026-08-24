---
name: inspect
description: Read the current QGIS project — layers, attribute fields, CRS, canvas extent. Load this whenever you need facts about the project before answering or acting.
tools: [list_layers, describe_layer, get_canvas_extent]
---

# Reading the project

These tools only read. They never modify the project, so use them freely and
without asking the user for permission.

## When to look before acting

- The user refers to a layer by name — confirm it exists with `list_layers` and
  use the exact name you get back.
- The user asks about data ("which fields", "how many objects", "what CRS") —
  answer from `describe_layer`, never from memory or guesswork.
- You are about to run any geoprocessing on a layer — check its CRS first.

## Coordinate reference systems

Both tools report `crs_is_geographic`. When it is true the layer measures in
degrees, not metres, and any distance you pass to a processing algorithm will be
read as degrees. `describe_layer` also returns `suggested_metric_crs` — the CRS to
reproject into when the user asks for metres.

This single fact causes more silently wrong results than anything else in QGIS.
Check it before planning, not after a step fails.

## Working with results

- Layer names are case-sensitive when passed to other tools. Copy them verbatim.
- If a layer name is not found, the tool returns the list of available names —
  use it to pick the right one or to ask a single clarifying question.

## Cost

Reading is cheap but not free. Call `list_layers` once per task, not before every
step; remember what you already learned within the same task.
