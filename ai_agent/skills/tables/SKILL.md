---
name: tables
description: Tabular data — preview a CSV, load it as a table or as points from lon/lat (x/y, WKT) columns, attach a table to a layer by a key field (join), list or remove joins. Load this for "join this CSV by code", "attach the population table to the districts", "make points from this CSV".
tools: [preview_table, load_table, join_table, list_joins, remove_join]
---

# Tables and joins

## Look before loading

Start from `preview_table` when the request names a file: it tells the
delimiter, the columns with the types QGIS will give them, the first rows and
the columns that look like coordinates. Use the column names exactly as it
returns them. The other tools read the file themselves, so a preview is not
required when the user already named the columns.

## Points from a table

`load_table` with `x_field` and `y_field` (or `wkt_field`) builds a layer that
stays linked to the file. Longitude is x, latitude is y. Without coordinate
arguments it recognises lon/lat and x/y columns by name; `table_only=true`
loads a plain table instead.

The CRS is the one the numbers were *written in*, not the project's. Values
within ±180/±90 are degrees, EPSG:4326, and that is filled in for you. Large
numbers (hundreds of thousands, millions) are projected — UTM, a national grid
— and need `crs`; ask the user or look at the file's documentation via `web`
when nothing tells you which. Never guess EPSG:3857 for such numbers: a wrong
projected CRS puts every point in the wrong country without an error.

## Join or new layer

- `join_table` — a live join. The layer gains the table's fields; nothing is
  copied, so an edited CSV shows up after reload, and `remove_join` undoes it.
  This is what "attach", "add the population to the districts" means.
- Processing `native:joinattributestable` — a new layer with the fields
  written in. Use it only when the user wants a separate result or a file
  to export, or when the joined values must be edited or survive without the
  table.

`table` takes a project layer or a file path. Pass the path directly when the
CSV is not loaded yet: the join loads it as a table in the same step. A file
that is already a layer in the project is reused, not loaded twice.

Attached fields are named `<table>_<field>` by default. Give `prefix` for
shorter names ("" for none) and `fields` to attach only the columns asked for —
a census table with forty columns makes the attribute table unusable.

## Keys

A join compares keys as text. Integer 1 and text "1" match; text "007" and
integer 7 do not. Before joining, compare the two key fields with
`get_field_values` or the preview when the request leaves doubt:

- leading zeros: codes like 007 are loaded as text and keep their zeros. If
  the layer stores the same codes as numbers, join on a virtual field
  (`fields` skill): `lpad(to_string("code"), 3, '0')` on the layer, or
  `to_int("code")` on the table;
- spaces and letter case: a virtual field with `trim()` / `upper()`;
- names as keys break on spelling ("St. Petersburg" vs "Saint Petersburg");
  prefer codes when both sides have them.

`join_table` refuses a join where no key matches and says why. A partial match
is allowed: its result reports `matched_keys`, `unmatched_keys` and samples.
Tell the user how many features got no data and show a few of those keys —
silence here reads as "all joined".

## Afterwards

`list_joins` reports every join with the match counts; use it to verify.
Styling or labelling by an attached field uses its full name, e.g.
`population_pop2020`. Attached fields are read-only on the layer: `edit` and
`fields` change the layer's own columns, not the table's.
