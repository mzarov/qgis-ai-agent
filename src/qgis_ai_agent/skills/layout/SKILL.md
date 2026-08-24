---
name: layout
description: Build and edit QGIS print layouts — pages, map frames, legends, scale bars, titles and captions. Load this for any request about a printable map or layout.
tools: [create_layout, add_map, add_legend, add_scale_bar, add_label]
---

# Composing a print layout

## Page geometry

- Coordinates are in millimetres, measured from the top-left corner of the page.
- A4: 210x297 portrait, 297x210 landscape.
- A3: 297x420 portrait, 420x297 landscape.

You may omit `x`, `y`, `width` and `height` on any tool. When omitted, the layout
engine places the item inside the correct zone and avoids overlapping existing
items. Omitting them is usually better than guessing coordinates.

## Order of steps

`add_legend` and `add_scale_bar` both attach themselves to a map frame. If the
layout has no map yet, call `add_map` before them.

## Existing layouts

- To change a layout that already exists, do not call `create_layout`. Reuse the
  exact `layout_name` and add or adjust items.
- Call `create_layout` only when the user explicitly asks for a new layout.
- When the user says "there", "on that layout" or similar, resolve it to a
  concrete layout name from the project rather than assuming.

## Text on the map

Always pass a semantic `role` to `add_label`:

| Role       | Use for                                    |
| ---------- | ------------------------------------------ |
| `title`    | the map title                              |
| `subtitle` | a secondary line under the title           |
| `footer`   | source, author, date, scale note           |
| `label`    | only when none of the above fits           |

Role-aware labels are positioned and sized automatically. A generic `label`
without a role floats and usually looks wrong — avoid it unless the semantics are
genuinely unknown.

## Scale bar

Leave `units_per_segment` and `segment_count` unset unless the user explicitly
asked for specific divisions. The tool picks readable values from the map scale
and shrinks the bar if it would not fit the page.

## Clarifications

Ask at most one short clarifying question, and only when you genuinely cannot
proceed — for example when the title text is missing. Otherwise choose a sensible
default and say what you chose.
