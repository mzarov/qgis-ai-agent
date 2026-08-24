---
name: inspect
description: Read the current QGIS project — layers, attribute fields, layouts, canvas extent. Load this whenever you need facts about the project before answering or acting.
tools: [list_layers, describe_layer, list_layouts, inspect_layout, get_canvas_extent]
---

# Reading the project

These tools only read. They never modify the project, so use them freely and
without asking the user for permission.

## When to look before acting

- The user refers to a layer or layout by name — confirm it exists with
  `list_layers` / `list_layouts` and use the exact name you get back.
- The user asks about data ("which fields", "how many objects", "what CRS") —
  answer from `describe_layer`, never from memory or guesswork.
- The user asks to change an existing layout — call `inspect_layout` first so you
  know what is already on the page and do not duplicate elements.
- The user asks what the map will show — `get_canvas_extent` returns the extent a
  new map frame will receive.

## Working with results

- Layer and layout names are case-sensitive when passed to other tools. Copy them
  verbatim from the tool result.
- `inspect_layout` returns `zones` (top_band, content, legend, footer) with the
  usable rectangle for each. Prefer placing new items inside a zone over inventing
  coordinates.
- If a layer name is not found, the tool returns the list of available names —
  use it to pick the right one or to ask a single clarifying question.

## Cost

Reading is cheap but not free. Call `list_layers` once per task, not before every
step; remember what you already learned within the same task.
