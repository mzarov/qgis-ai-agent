---
name: layout
description: Print output — a page with map, title, legend, scale bar, north arrow or picture, exported to PDF or PNG. Load this for "print", "PDF", "A3", "map sheet", "poster"; a data file is export_layer in project.
tools: [list_layouts, describe_layout, render_layout, create_layout, add_layout_item, configure_layout_item, remove_layout_item, export_layout]
---

# Print layouts

A layout is a page composed of items: a map, labels, a legend, a scale bar.
Everything is measured in **millimetres from the top-left corner of the page**.
There is no grid and no fixed zones — you place items yourself and then look at
the result.

## The workflow

1. `create_layout` — page size and orientation. Landscape A4 (297×210) is the
   default and fits most single-map sheets. Landscape sizes in mm: A5 210×148,
   A4 297×210, A3 420×297, A2 594×420, Letter 279.4×215.9; portrait swaps them.
   Scale every position below to the page you chose.
2. `add_layout_item` for each piece, all queued in the same turn. Give every
   item a readable `id` (`map-1`, `title`) — you will address them later.
3. After the user applies, the verification pass runs. If `render_layout` is
   in your tool list, call it and **look at the image**; otherwise judge the
   page from the `describe_layout` geometry. Fix what you find with
   `configure_layout_item` (move, resize, retext) or `remove_layout_item` —
   those fixes queue into a new plan.
4. `export_layout` to PDF or PNG when the user wants a file.

When you can see images, the looking step is not optional politeness — it is
how composition quality happens. Numeric positions from `describe_layout` tell
you *whether* boxes overlap; only the rendered image tells you whether the page
*reads well*. Without `render_layout`, check the numbers against the guidance
below: margins, overlaps, the map's share of the page.

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
- `north_arrow`: `style` — `simple` (default), `compass`, `triangle`; about
  15×15 mm in a corner of the map
- `picture`: `path` — an image file on disk (a logo, a locator map)

A legend, a scale bar and a north arrow need a map in the layout — queue the
map first, in the same batch is fine: items are applied in queue order.

## Honesty

Queued items are not visible yet — never describe the layout as built before
the user applies. After export, give the user the exact path. There is no
table or overview-map item: say so plainly instead of faking one with labels.
