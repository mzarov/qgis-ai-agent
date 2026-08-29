---
name: fields
description: Change the attribute schema of a layer — add, rename and delete fields, including virtual fields computed from an expression. Load this when the request is about columns rather than values.
tools: [add_field, rename_field, delete_field]
---

# The attribute schema

These tools change which columns a layer has. Changing the values inside them
is the `edit` skill; computing a whole new derived layer is `processing`.

## Real fields and virtual fields

`add_field` does two different things depending on `expression`:

- **without it** — a real column written into the data source. It starts
  empty; fill it with `update_attributes` or `native:fieldcalculator`.
- **with it** — a virtual field: the expression is evaluated on the fly and
  the definition lives in the project, not in the file.

Prefer the virtual one when the value is derived — area, length, a formatted
label, a ratio between columns. It cannot go stale, it does not touch the
user's data, and it costs nothing to remove. Reach for a real field when the
value has to survive export to a file or be edited by hand.

```
add_field(layer_name="Districts", name="area_ha", expression="$area / 10000")
```

Length and area in a virtual field follow the layer CRS — on a geographic
layer the number is meaningless, so reproject first, exactly as in the
processing skill.

## Types

`text`, `integer`, `double`, `boolean`, `date`. Pick by what the value *is*,
not by what is convenient: a number stored as text stops sorting and
classification from working. When unsure, read the real values with
`get_field_values` first.

## Deleting

`delete_field` is destructive: the column and every value in it go away, and
the plugin asks the user a second time. Check with `get_field_values` that the
column really is the one meant — names like `id`, `fid`, `gid` often carry the
provider's identity and breaking them breaks the layer.

## Honesty

Schema changes are committed to the provider. A failed commit rolls the layer
back and the error says why — a read-only source (a joined layer, a service)
is the usual reason, and that is worth telling the user plainly instead of
retrying.
