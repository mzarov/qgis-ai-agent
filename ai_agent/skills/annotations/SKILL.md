---
name: annotations
description: Notes drawn directly on the map — text labels and markers above all layers. Load this for "mark this", "label that spot", "point at".
tools: [add_annotation, list_annotations, remove_annotation]
---

# Map annotations

Annotations are drawings on top of the map, not data: they live in the
project's annotation layer, sit above every data layer, and vanish with the
project, never with a layer. Use them to point at things; anything that should
survive analysis belongs in a layer with attributes instead.

## Placing

`add_annotation` takes lon/lat in EPSG:4326 by default and reprojects to the
project CRS itself. Where do coordinates come from? Never invented:

- a place the user named → `geocode` from the `web` skill first
- "here" / the current view → `get_canvas_extent`, take the centre
- a feature → `query_layer` with `$x`/`$y` expressions

For a text note pass `text`; `size` and `color` are optional and default to a
readable label. A `marker` is a plain point symbol for "right here".

## Housekeeping

`list_annotations` returns ids; `remove_annotation` deletes one by id. There
is no edit — remove and place again, it is one step each way.
