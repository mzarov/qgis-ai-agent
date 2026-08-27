# Usage

Open the panel from the **QGIS AI Agent** menu entry or the toolbar icon, type a
request, press Enter. Shift+Enter breaks the line; while the agent works, the
send button becomes a stop button.

## Asking about the project

Reading runs immediately, no confirmation:

- *what layers do I have?*
- *which fields does the roads layer have, and what is in `highway`?*
- *how many motorway roads are there?*
- *which river is the longest?* — length and area come from the geometry
  itself; no length column is needed
- *why are the cities red?* — the agent reads the actual renderer instead of
  guessing

## Changing things

Writing collects into a plan card; press **Apply** to run it, **Cancel** to
drop it:

- *make the rivers blue* / *roads as thin grey dashed lines*
- *colour the districts by population, 7 classes, Viridis*
- *label the cities with names, bold, 12 pt, white halo* — one step, not four
- *build a 500 m buffer around the schools* — on a degree-based layer the agent
  reprojects first, on its own
- *load /data/roads.geojson into the Background group*
- *download the cafes in Tver from OSM* / *roads except unpaved ones in the
  current view*
- *clip the roads by the city boundary, compute the length and save the
  project* — a whole chain lands in one plan card

## Conversations

Conversations persist across QGIS restarts and are bound to the project: the
**Conversations** menu lists only the ones started in the currently open
project. The title is your first message. Restoring a conversation restores the
model's context too — a follow-up like *and how many are there?* keeps working.

## When something goes wrong

- A tool error does not kill the run: the agent reads the error and corrects
  itself — a wrong layer name gets the list of real ones.
- The stop button aborts the run immediately and discards any planned changes.
- Overpass (the OSM service) is public and sometimes busy; a refusal is not a
  plugin bug — retry later or narrow the query.
- A small local model (7–8B) will fumble the tool calls. The sensible minimum
  is a ~30B-class model with function calling.
