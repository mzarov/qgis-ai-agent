---
name: sql
description: One SQL SELECT over the project's vector layers — joins between layers, GROUP BY statistics, spatial joins (which points fall in which polygon), answered as a table or kept as a live query layer. Load this when a question combines layers or groups data and one query_layer call cannot answer it.
tools: [query_sql, create_sql_layer]
---

# SQL over the project's layers

## Which tool

- `query_sql` answers and changes nothing. Prefer it to a chain of
  `query_layer`, aggregates and Processing runs when the question joins
  layers, groups by a field, or counts what lies where — one statement does it.
- `create_sql_layer` keeps the result as a new virtual layer that stays live
  like a view. Use it when the user wants the result on the map, to style or
  export it, not for an answer in words. Run the query through `query_sql`
  first when you are not sure of it.
- A single-layer count, sum or top N is still `query_layer`; a field written
  onto an existing layer is `fields` or Processing.

## Dialect

SQLite with SpatiaLite functions: `ST_Area`, `ST_Length`, `ST_Intersects`,
`ST_Contains`, `ST_Within`, `ST_Distance`, `ST_Buffer`, `ST_Centroid`,
`ST_Transform`, `ST_X`, plus `count`, `sum`, `avg`, `group_concat`, `round`,
`CASE`.

- A table is a project layer: its name in double quotes, exactly as in the
  project — `FROM "districts"`. When two layers share a name, write the layer
  id in double quotes instead.
- Quote field names with capitals, spaces or dashes: `"Pop 2020"`. Text
  values take single quotes: `WHERE kind = 'lyceum'`.
- Every layer's geometry column is `geometry`.
- Integer division truncates: `pop * 1.0 / households`.

## Units and CRS

SQL ignores the project's ellipsoid: `ST_Area` and `ST_Length` return the
layer's CRS units, square degrees on EPSG:4326. Transform to a local metric
CRS first — the one the Measurements line names, else `suggested_metric_crs`
from `describe_layer` — by its EPSG number:
`ST_Area(ST_Transform(geometry, 32637)) / 1e6` for km². Never 3857: it
inflates sizes threefold at 55° N.

Two layers in different CRSs match nothing until one is transformed:
`ST_Contains(d.geometry, ST_Transform(s.geometry, 4326))`. Read each layer's
CRS from the project context.

## Spatial joins

```sql
SELECT d.name, count(s.geometry) AS schools
FROM "districts" d LEFT JOIN "schools" s ON ST_Contains(d.geometry, s.geometry)
GROUP BY d.name ORDER BY schools DESC
```

LEFT JOIN keeps the districts with none. On layers of thousands of features
add the spatial index to the join: `AND s._search_frame_ = d.geometry`.

## Results

`query_sql` returns at most 200 rows with the total count: aggregate and
`ORDER BY ... LIMIT` rather than list everything. Geometry never comes back;
select numbers from it instead.

For `create_sql_layer`, the first geometry column of the result becomes the
layer's geometry: select one, `ST_Buffer(geometry, 100) AS geometry`. Every
layer the query reads must exist now — one queued in the same batch does not
until Apply.
