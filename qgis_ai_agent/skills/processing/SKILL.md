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
   are English even when the QGIS interface is localised. Searching in the user's
   language usually returns nothing and costs a wasted round trip.
2. `describe_processing` with the chosen id → returns the exact parameter names,
   types, whether each is optional, and the allowed values for enums.
3. `run_processing` with those exact parameter names.

Guessing a parameter name produces a failed run and a confusing error for the
user. One extra read call is much cheaper than a wrong write.

## The map most requests land on

Search still needs the right English words, and a few everyday tasks are not
algorithms at all. Start from this table, then confirm with `describe_processing`
— the ids below are stable QGIS core, but the parameters are not worth guessing.

**Vector overlay**

| Task | id |
|---|---|
| clip a layer by the boundary of another | `native:clip` |
| intersection of two layers | `native:intersection` |
| union keeping the attributes | `native:union` |
| subtract one layer from another | `native:difference` |
| merge several layers into one | `native:mergevectorlayers` |
| dissolve boundaries, grouped by a field | `native:dissolve` |

**Geometry**

| Task | id |
|---|---|
| buffer | `native:buffer` |
| centroids of polygons | `native:centroids` |
| convex hull | `native:convexhull` |
| simplify geometry | `native:simplifygeometries` |
| repair broken geometry | `native:fixgeometries` |
| reproject a layer | `native:reprojectlayer` |
| split multiparts into separate features | `native:multiparttosingleparts` |
| Voronoi polygons | `native:voronoipolygons` |

**Attributes and joins**

| Task | id |
|---|---|
| add or recompute a field | `native:fieldcalculator` |
| join a table on a shared field | `native:joinattributestable` |
| join by location | `native:joinattributesbylocation` |
| join the nearest feature | `native:joinbynearest` |
| keep or rename fields | `native:refactorfields` |
| statistics by group | `qgis:statisticsbycategories` |
| how many points fall in each polygon | `native:countpointsinpolygon` |

**Selection**

| Task | id |
|---|---|
| extract by condition | `native:extractbyexpression` |
| extract by location | `native:extractbylocation` |
| extract by extent | `native:extractbyextent` |

**Raster**

| Task | id |
|---|---|
| raster calculator | `native:rastercalc` |
| clip a raster by a mask | `gdal:cliprasterbymasklayer` |
| reproject a raster | `gdal:warpreproject` |
| merge rasters | `gdal:merge` |
| slope, aspect, hillshade | `native:slope`, `native:aspect`, `native:hillshade` |
| contour lines | `gdal:contour` |
| raster statistics per polygon | `native:zonalstatisticsfb` |
| sample raster values at points | `native:rastersampling` |
| raster to polygons | `gdal:polygonize` |
| vectors to raster | `gdal:rasterize` |

## What is not an algorithm at all

Three of the most common requests are not algorithms, and searching for them leads
somewhere else entirely. `search_processing("area")` returns
`native:serviceareafrompoint` first — a travel-time catchment, not an area.

Area, length, perimeter and coordinates are **expressions**, not algorithms:

- to compute and store in a field — `native:fieldcalculator` with `FORMULA`
- to just read the value, changing nothing — `query_layer` from the `inspect` skill

| Wanted | Expression |
|---|---|
| area of a polygon | `$area` |
| length of a line, perimeter | `$length`, `$perimeter` |
| coordinates of a point | `$x`, `$y` |
| area in hectares | `$area / 10000` |

The units of `$area` and `$length` are the units of the layer CRS. On a geographic
system that gives square degrees, which is meaningless: run
`native:reprojectlayer` into a metric CRS first, then measure.

NDVI and other band arithmetic is not a separate algorithm either, but
`native:rastercalc` with an expression like `("scene@4" - "scene@3") / ("scene@4" + "scene@3")`,
where `@N` is the band number and the name before `@` is the layer name in the project.

The raster calculator has a catch: `EXTENT`, `CELL_SIZE` and `CRS` are required, and
there is nowhere to get them but the source raster. Call `describe_layer` on it
first — that gives `extent` and `crs` — and only then run. Take the cell size from
`describe_layer` of the same raster rather than inventing one: a foreign value
silently resamples the result.

## Analysis recipes

Named chains for the analysis requests that otherwise take a round of
exploration. Ids are stable core QGIS; still confirm parameters with
`describe_processing` before running.

**Cluster points (k-means).** `native:kmeansclustering` with `INPUT` and
`CLUSTERS` adds a `CLUSTER_ID` field. Colour the result with `set_categories`
on `CLUSTER_ID`. When the user has no cluster count in mind, prefer DBSCAN.

**Cluster points by density (DBSCAN).** `native:dbscanclustering` takes `EPS`
(a distance in layer units — metric CRS first, as always) and `MIN_SIZE`.
Noise points get NULL `CLUSTER_ID`; mention that instead of hiding it.

**Hotspots as a heatmap.** `qgis:heatmapkerneldensityestimation` over the
points: `RADIUS` in layer units, `PIXEL_SIZE` sensible for the extent (a city
at 10 m, a region at 100 m). Then `set_raster_style` with a pseudocolour ramp.
The input must be in a metric CRS or the radius is degrees.

**Hotspots as a grid.** When the user wants countable cells rather than a
smooth surface: `native:creategrid` (hexagon type, `HSPACING`/`VSPACING`
metric, `EXTENT` from `describe_layer` of the points) → 
`native:countpointsinpolygon` → `set_graduated` on `NUMPOINTS` →
`native:extractbyexpression` with `NUMPOINTS > 0` if the empty cells drown
the picture.

**Regression.** Core QGIS ships no regression algorithm. For a simple linear
relation between two fields the honest route is `run_python` with numpy
(`numpy.polyfit(x, y, 1)` over values read from the layer) and a clear
statement of what was fitted. Do not fake it with the raster calculator.

## Terrain and interpolation recipes

**Slope / aspect / hillshade.** The DEM must be in a metric CRS —
`gdal:warpreproject` first if `describe_layer` says degrees. Then
`native:slope`, `native:aspect` or `native:hillshade`; hillshade takes
`AZIMUTH` (315 is the cartographic default) and `V_ANGLE`. Style slope with
`set_raster_style` pseudocolour.

**Contour lines.** `gdal:contour` with `INTERVAL` in the DEM's height units
and `BAND` 1. Label them with `set_labels` on the `ELEV` field.

**IDW interpolation.** Prefer `gdal:gridinversedistance` — it takes the points
layer and `Z_FIELD` by name, no special syntax. Set `-outsize` via
`WIDTH`/`HEIGHT` if offered; otherwise defaults are fine for a first look.

**TIN interpolation.** `qgis:tininterpolation` takes its input as one packed
string: `INTERPOLATION_DATA` is
`"<layer source>::~::0::~::<field index>::~::0"` — layer source, use-z flag,
the numeric index of the value field, and the geometry type. Get the field
index from `describe_layer` (fields are listed in order, starting at 0). It
also requires `EXTENT` and `PIXEL_SIZE`, both from the points layer. When
this feels fragile, `gdal:gridlinear` is the simpler cousin.

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
               parameters={"INPUT": "Cities", "TARGET_CRS": "EPSG:32641"},
               output_name="Cities UTM 41")
run_processing(algorithm_id="native:buffer",
               parameters={"INPUT": "Cities UTM 41", "DISTANCE": 500},
               output_name="Buffer 500 m")
```

`describe_layer` returns `suggested_metric_crs` for exactly this — use it as
`TARGET_CRS` rather than picking a CRS yourself. If you queue a metric distance on
a geographic layer anyway, the step is rejected and the error tells you the same
thing; act on it instead of reporting it.

## Chaining steps

A queued step has not run yet, so its output layer does not exist while you are
planning. Give each step an `output_name` and reference that name in the next
step — this is the only reliable way to chain two runs in one plan.

Queue **every** step of the chain in the same turn. Writing out "first we reproject,
then we build the buffer" and stopping there leaves the user with
nothing to confirm — the plan only exists once `run_processing` has been called
for each step.

## Results

`run_processing` loads its output into the project by default, so the new layer
becomes available to later steps. Pass `load_output: false` only when the user
explicitly wants the result not added.
