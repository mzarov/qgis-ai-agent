---
name: project
description: Manage the project itself — add and remove layers, rename, hide, group and reorder them, change project CRS, zoom the map, save the project. Load this to set a workflow up or to finish it.
tools: [zoom_to_layer, add_layer, remove_layer, configure_layer, configure_project, save_project]
---

# The project as a workspace

The `inspect` skill reads the project and `style` paints it; this skill changes
what the project *is* — which layers it holds, how they are arranged, where it is
saved.

| Ask | Tool |
|---|---|
| «загрузи файл», «добавь слой» | `add_layer` |
| «убери слой», «удали лишний» | `remove_layer` |
| «переименуй», «спрячь», «в группу», «подними наверх» | `configure_layer` |
| «смени проекцию проекта», «назови проект» | `configure_project` |
| «покажи слой», «приблизь к» | `zoom_to_layer` |
| «сохрани проект» | `save_project` |

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

Draw order is what `position` controls: **0 is the top of the group and draws over
everything below it.** "Подними реки наверх" is `position: 0`; "спрячь под дороги"
means giving the rivers a larger position than the roads.

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
