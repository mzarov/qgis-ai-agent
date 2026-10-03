---
name: draw
description: Create point, line or polygon features from coordinates, in a new scratch layer or an existing one. Load for "a point at 55.75, 37.62", "a line between these towns", "a 500 m buffer around this address"; a purely visual mark is annotations.
tools: [draw_features]
---

# Drawing features from coordinates

`draw_features` turns coordinates into real features with attributes: they
show in the attribute table, can be styled and labelled, and feed processing.
That is the difference from an annotation, which is only a drawing.

## Coordinates are never invented

Every vertex comes from the user, a tool result or an existing feature:

- **Typed numbers.** People and web maps write latitude first:
  "55.75, 37.62" means latitude 55.75, longitude 37.62. `coordinates` are
  `[x, y]` = `[longitude, latitude]`, so that point is `[[37.62, 55.75]]`.
  Swap only when the user's order is lat, lon; when both numbers are under 90
  and the order is unclear, decide by the region of the project and say which
  order you took.
- **A place or an address.** `geocode` from the `web` skill, one call per
  place; it returns `lat` and `lon` separately — put them as `[lon, lat]`.
- **An existing feature.** `query_layer` with `$x`/`$y`, or
  `x(centroid($geometry))`/`y(centroid($geometry))` for lines and polygons —
  those come in the layer's CRS, so pass that CRS as `crs`.
- **Projected numbers** (metres from a survey, a CAD drawing) — pass their
  CRS as `crs`. The layer reprojects them itself.

## Where the features go

- By default draw into a **new scratch layer**: `new_layer_name`, named after
  the content ("Town hall", "Route A–B"). One layer per geometry kind.
- Put **all features of a new layer in one call**. A queued step has not run
  yet, so a second `draw_features` cannot append to a layer that only a
  queued step creates.
- `layer_name` appends to an **existing layer** of the same geometry, only
  when the user asks for it. Its CRS and fields stay as they are; coordinates
  are transformed into its CRS. A file or database layer is committed to its
  source — the plugin asks the user a second time, and Undo cannot take it
  back. A scratch layer has no such prompt.

## Attributes

Give each feature a `name` attribute when the request names it — the user
will see it in the table and in labels. Field types are inferred from the
values; declare `fields` only for an empty layer or a type the values cannot
show (a `date` written as "2025-05-09"). For an existing layer the attribute
names must be its own fields; add a field with the `fields` skill first.

## Lines and polygons

A line between places is **one** feature with the vertices in travel order.
It is a straight segment in the layer's CRS, not a road route — say so when
the user may expect one. A polygon takes its ring in order around the
boundary; the ring closes itself.

## Geocode → draw → buffer

A metric buffer around an address chains three skills; load `web`, `draw` and
`processing` together. `layer_crs: "utm"` keeps the input in lon/lat but
stores the layer in the local UTM zone, so a later `DISTANCE` is in metres and
no reprojection step is needed:

```
geocode(place="Town hall, Kazan")                  → lat 55.79, lon 49.11
draw_features(new_layer_name="City Hall", geometry="point", layer_crs="utm",
              features=[{"coordinates": [[49.11, 55.79]],
                         "attributes": {"name": "City Hall"}}])
run_processing(algorithm_id="native:buffer",
               parameters={"INPUT": "City Hall", "DISTANCE": 500},
               output_name="City Hall 500 m")
```

Queue the draw and the buffer in the same turn. A layer drawn in EPSG:4326
measures in degrees: buffer it only after `native:reprojectlayer`, as the
processing skill says.

## After applying

A scratch layer lives in memory until QGIS closes — say so, and offer
`export_layer` from the project skill when the user wants to keep it.
