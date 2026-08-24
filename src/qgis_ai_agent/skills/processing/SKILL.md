---
name: processing
description: Run QGIS geoprocessing algorithms — buffers, clips, joins, reprojection, statistics, raster maths. Load this for any request that transforms or analyses data.
tools: [search_processing, describe_processing, run_processing]
---

# Geoprocessing

QGIS ships over a thousand algorithms. You are not expected to know their
identifiers or signatures — discover them at runtime.

## The three-step rule

Never call `run_processing` from memory. Always:

1. `search_processing` with words describing the task → returns candidate ids
   such as `native:buffer`. **Search in English** — algorithm ids, tags and groups
   are English even when the QGIS interface is localised. Searching in Russian
   usually returns nothing and costs a wasted round trip.
2. `describe_processing` with the chosen id → returns the exact parameter names,
   types, whether each is optional, and the allowed values for enums.
3. `run_processing` with those exact parameter names.

Guessing a parameter name produces a failed run and a confusing error for the
user. One extra read call is much cheaper than a wrong write.

## Parameters

- Input layers are given by their project layer name. Confirm the name with
  `list_layers` first — names are case-sensitive.
- **Enum parameters take a number, not a label.** `describe_processing` returns
  them as `{"value": 0, "label": "Round"}` pairs — pass the `value`.
- For an output that should become a new layer, pass `'TEMPORARY_OUTPUT'` unless
  the user asked for a file on disk.

## Metres on a geographic CRS

`list_layers` and `describe_layer` report `crs_is_geographic`. When it is true the
layer measures in degrees, and a distance in metres is meaningless — 500 there
means 500 degrees.

Do not hand this back to the user as a problem. Fix it yourself with a two-step plan:

```
run_processing(algorithm_id="native:reprojectlayer",
               parameters={"INPUT": "Города", "TARGET_CRS": "EPSG:32641"},
               output_name="Города UTM 41")
run_processing(algorithm_id="native:buffer",
               parameters={"INPUT": "Города UTM 41", "DISTANCE": 500},
               output_name="Буфер 500 м")
```

`describe_layer` returns `suggested_metric_crs` for exactly this — use it as
`TARGET_CRS` rather than picking a CRS yourself. If you queue a metric distance on
a geographic layer anyway, the step is rejected and the error tells you the same
thing; act on it instead of reporting it.

## Chaining steps

A queued step has not run yet, so its output layer does not exist while you are
planning. Give each step an `output_name` and reference that name in the next
step — this is the only reliable way to chain two runs in one plan.

## Results

`run_processing` loads its output into the project by default, so the new layer
becomes available to later steps. Pass `load_output: false` only when the user
explicitly wants the result not added.
