---
name: quality
description: Check a layer for data errors — invalid, empty or repeated geometries, empty fields, coordinates that do not fit the CRS, a missing CRS, raster nodata. Load this for "check my data", "is this layer clean?", "find broken geometries", or before analysing someone else's data.
tools: [check_layer]
---

# Checking data

Run `check_layer` first, once per layer the user means; with no layer named,
the active one from the project context. Do not judge quality from
`describe_layer` or by sampling features — they see none of this.

## Reporting

Tell the user what was found in plain words, counts first, with a few sample
ids: "3 polygons cross themselves (ids 12, 40, 77)". An empty `problems` means
the layer is clean — say so plainly; `missing_values` is worth a sentence only
when a field the user cares about has gaps. When `partial` is true, say that
only the first features were checked.

## Fixing

Report first, then propose the fixes from `suggestions` as queued steps —
never fix silently. Load `processing` for the algorithms they name.

- `native:fixgeometries`, `native:removenullgeometries`,
  `native:deleteduplicategeometries` and `native:assignprojection` write a
  **new layer**; the source stays untouched. Say so when proposing them. Never
  overwrite the source or change it in place (`edit`, `run_python`) unless the
  user asks for exactly that.
- A wrong CRS is assigned, never reprojected: `native:reprojectlayer`
  transforms the numbers it is given, so wrong numbers stay wrong. When the
  right CRS is not obvious (a UTM zone, a national grid), ask the user instead
  of guessing.
- Repeated geometries may carry different attributes; show the sample groups
  before dropping copies.
