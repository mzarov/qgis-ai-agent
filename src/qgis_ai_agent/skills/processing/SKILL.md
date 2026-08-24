---
name: processing
description: Run QGIS geoprocessing algorithms — buffers, clips, joins, reprojection, statistics, raster maths. Load this for any request that transforms or analyses data rather than laying it out.
tools: [search_processing, describe_processing, run_processing]
---

# Geoprocessing

QGIS ships over a thousand algorithms. You are not expected to know their
identifiers or signatures — discover them at runtime.

## The three-step rule

Never call `run_processing` from memory. Always:

1. `search_processing` with words describing the task → returns candidate ids
   such as `native:buffer`.
2. `describe_processing` with the chosen id → returns the exact parameter names,
   types, whether each is optional, and the allowed values for enums.
3. `run_processing` with those exact parameter names.

Guessing a parameter name produces a failed run and a confusing error for the
user. One extra read call is much cheaper than a wrong write.

## Parameters

- Input layers are given by their project layer name. Confirm the name with
  `list_layers` first — names are case-sensitive.
- For an output that should become a new layer, pass `'TEMPORARY_OUTPUT'` unless
  the user asked for a file on disk.
- Distances and buffer sizes are in the units of the layer's CRS. If the layer is
  in a geographic CRS (EPSG:4326 and similar), a distance in metres will not work
  as expected — check the CRS with `describe_layer` and reproject first, or tell
  the user why the result would be wrong.

## Results

`run_processing` loads its output into the project by default, so the new layer
becomes available to later steps and to layout tools. Pass `load_output: false`
only when the user explicitly wants the result not added.

After a run, the new layer exists but you have not seen it — use `describe_layer`
if you need its fields or extent for a following step.

## Chaining with other skills

A request like "буфер вокруг дорог и собери макет" spans two domains: run the
geoprocessing first, then load the `layout` skill and build the layout on top of
the resulting layer.
