---
name: layout
description: Build print layouts — a map sheet with a title, legend and scale bar — and export them to PDF or PNG. Load this when the user wants a map for printing or a file to hand over.
tools: [list_layouts, describe_layout, render_layout, create_layout, add_layout_item, configure_layout_item, remove_layout_item, export_layout]
---

# Print layouts

A layout is a page composed of items: a map, labels, a legend, a scale bar.
Everything is measured in **millimetres from the top-left corner of the page**.
There is no grid and no fixed zones — you place items yourself and then look at
the result.

## The workflow

1. `create_layout` — page size and orientation. Landscape A4 (297×210) is the
   default and fits most single-map sheets.
2. `add_layout_item` for each piece, all queued in the same turn. Give every
   item a readable `id` (`map-1`, `title`) — you will address them later.
3. After the user applies, the verification pass runs: call `render_layout`
   and **look at the image**. Fix what you see with `configure_layout_item`
   (move, resize, retext) or `remove_layout_item` — those fixes queue into a
   new plan.
4. `export_layout` to PDF or PNG when the user wants a file.

The looking step is not optional politeness — it is how composition quality
happens. Numeric positions from `describe_layout` tell you *whether* boxes
overlap; only the rendered image tells you whether the page *reads well*.

## Composition guidance

These are starting points, not rules the plugin enforces — adjust by eye:

- keep ~10 mm of margin on every side; nothing touches the page edge
- the map is the hero: give it most of the page
- the title is a `label` in the top band, font_size 18–24
- the legend goes beside or below the map, not across its middle; on a busy
  map a corner placement over water or empty area works
- the scale bar sits in the bottom-left of the map area
- a small attribution label (font_size 6–8) in the bottom-right corner when
  the data needs crediting (OSM does)

On an A4 landscape page (297×210) a sane single-map start is: title at
(10, 8) width 277, map at (10, 24) size 200×170, legend at (218, 24) width
69, scale bar at (14, 180).

## Item properties

- `map`: `extent` — `canvas` (default, what the user sees) or a layer name
  to frame that layer
- `label`: `text` (required), `font_size`
- `legend`: `title`, `map_id` (defaults to the first map)
- `scale_bar`: `style` — `single_box` (default), `double_box`, `ticks`,
  `numeric`; `map_id`

A legend and a scale bar need a map in the layout — queue the map first, in
the same batch is fine: items are applied in queue order.

## Honesty

Queued items are not visible yet — never describe the layout as built before
the user applies. After export, give the user the exact path. If a request
needs an item type that does not exist (north arrow, picture, table), say so
plainly — do not fake it with labels.
