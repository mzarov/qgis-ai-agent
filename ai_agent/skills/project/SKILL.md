---
name: project
description: Manage the project itself — add layers from files, basemaps and PostGIS, remove, rename, hide, group and reorder them, change project CRS, zoom the map, save the project. Load this to set a workflow up or to finish it.
tools: [zoom_to_layer, add_layer, add_basemap, add_service_layer, list_db_connections, list_db_tables, add_db_layer, remove_layer, reorder_layers, configure_layer, configure_project, save_project, export_layer, undo_last_apply, list_views, remember, list_notes, forget, save_bookmark, save_map_theme]
---

# The project as a workspace

The `inspect` skill reads the project and `style` paints it; this skill changes
what the project *is* — which layers it holds, how they are arranged, where it is
saved.

| Ask | Tool |
|---|---|
| "load a file", "add a layer" | `add_layer` |
| "add a basemap", "OSM background", "satellite under my layers" | `add_basemap` |
| "add a WMS/WFS layer", "from this service url" | `add_service_layer` |
| "undo that", "roll it back" | `undo_last_apply` |
| "remember this view", "save this look" | `save_bookmark`, `save_map_theme` |
| "load a table from the database", "from PostGIS" | `list_db_connections` → `list_db_tables` → `add_db_layer` |
| "drop a layer", "remove the spare one" | `remove_layer` |
| "rename", "hide", "into a group", "move to the top" | `configure_layer` |
| "change the project CRS", "name the project" | `configure_project` |
| "show me the layer", "zoom to" | `zoom_to_layer` |
| "save the project" | `save_project` |
| "save this layer to a file", "export to GeoJSON" | `export_layer` |

## Basemaps

`add_basemap` places the tile layer at the bottom of the tree, so it never
covers the data. Presets carry their attribution — repeat it to the user when
they ask about the source. "Подложка", "фон", "спутник" all mean a basemap;
`osm` is the safe default, `esri-imagery` is the satellite one. Tiles come from
public services and need internet; a blank layer usually means no connection,
not a wrong call.

## Web services

`add_service_layer` covers OGC services: `wms` returns rendered pictures,
`wfs` returns real features you can then query and style. The published layer
name comes from the service, not from you — if the user has not given it,
ask rather than guess. The plugin sends no credentials, so a service behind a
login will simply fail to load; say that plainly.

For plain tile basemaps use `add_basemap` instead — it is simpler and places
the layer at the bottom.

## Getting data out

`export_layer` writes a vector layer to disk: GeoPackage, GeoJSON, Shapefile
or CSV, picked from the path extension. Two options matter — `selected_only`
turns "export what I picked" into one call, and `crs` reprojects on the way
out, which is what "give me this in WGS84" means.

Saving the project and exporting a layer are different requests: the first
keeps the workspace, the second hands someone a file. Do not substitute one
for the other.

## Undo

Before every applied plan the plugin writes a snapshot of the project to a
temporary file. `undo_last_apply` reads it back, which restores layers,
styling and layouts.

Be honest about its reach: it restores the **project**, not data. Attribute
edits and deleted features from the `edit` skill live in the data source and
stay. Say so when offering it, so nobody expects a full time machine.

## Remembering the project

`remember` stores a durable fact about **this** project — what a cryptic field
holds, which CRS the client insists on, a naming convention. Notes come back
pinned into your context in every future conversation about the same project,
so they save the user from re-explaining their own data.

Store a note when the user says to, and when they state something that will
obviously matter next time ("POP2020 is the 2020 census"). Do not store what
QGIS can tell you — layer names, field lists, CRS are one read away and go
stale. Do not store instructions about how to behave; that is what the skills
are for.

One fact per note, written so it stands alone. `list_notes` shows them,
`forget` removes one by exact text.

## Bookmarks and map themes

`save_bookmark` remembers the current extent under a name; `save_map_theme`
remembers which layers are visible and how they look. `list_views` reports
both. Themes are what "save this look" means, and they are also what a layout
map item can be pinned to later.

## Databases

The plugin never sees database passwords: it can only use connections the user
already saved in the QGIS Browser. The path is always three steps —
`list_db_connections` to find the connection, `list_db_tables` for the exact
schema and table, `add_db_layer` to load. Never guess table names: they are
case sensitive and the listing is one cheap read away. If there are no saved
connections, tell the user to create one in Browser → PostgreSQL, do not ask
for credentials in chat.

## Finishing the job

A styling or processing task is not done when the layer looks right — it is done
when the user's project holds the result. If the run changed the project and the
user did not ask you to keep it unsaved, **queue `save_project` as the last step**.

The exception is a project that has never been saved: there `save_project` needs
an explicit `path`, and inventing a path for someone's disk is worse than asking.
In that case finish without saving and say plainly that the project is unsaved.

## Adding layers

`add_layer` takes a path and works out vector or raster from the extension. Pass
`kind` only when the extension lies or there is none.

A layer that QGIS cannot open comes back as an error naming the reason — a missing
file, an unreadable format, a broken source. Do not add the same file twice hoping
for a different result: read the reason and tell the user what is wrong.

Names must be unique in the project. Loading a second `roads.geojson` needs an
explicit `name`, otherwise the tool refuses before anything is queued.

## Arranging layers

`configure_layer` takes one `properties` bag: `name`, `visible`, `group`,
`position`. Set them all in one call rather than queueing the tool repeatedly for
one layer.

For the whole panel use `reorder_layers`: name the layers top to bottom in one
call — points first, then lines, then polygons, basemap last — and the tool does
the arithmetic. Do not queue a `position` per layer to arrange everything: six
absolute indices are six chances to invert the map.

For a single layer, draw order is what `position` controls: **0 is the top of the
group and draws over everything below it.** "Move the rivers to the top" is
`position: 0`; "tuck them under the roads" means giving the rivers a larger
position than the roads.

`group` moves the layer into a named group, creating it if it does not exist.
An empty string moves the layer back to the root.

## Changing the project CRS

`configure_project` with `crs` changes the projection the **map is drawn in**. It
does not reproject any data — layer CRS stays as it is, QGIS reprojects on the fly.
If the user wants the data itself reprojected, that is `native:reprojectlayer` in
the `processing` skill, not this tool.

## Reading before writing

`configure_layer` and `remove_layer` need the layer's exact name. `list_layers`
from the `inspect` skill gives it. Guessing a name produces an error listing the
real ones, which costs a round trip.
