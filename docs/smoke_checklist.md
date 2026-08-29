# Smoke Checklist

Manual verification in live QGIS — the part tests cannot cover: real PyQGIS
calls against layers and Qt painting. Everything else is closed by the
`tests/` suite.

## Technical check after edits

```bash
python3 -m unittest discover -s tests -t .
```

The suite runs without QGIS. If it is red, going into live QGIS is premature.

## Read tools without the agent

Open a project with layers, then **Plugins → Python Console**:

```python
from qgis_ai_agent.qgis_tools.registry import execute_tool
execute_tool("get_project_info", {})
execute_tool("list_layers", {})
execute_tool("describe_layer", {"layer_name": "LAYER_NAME"})
execute_tool("get_field_values", {"layer_name": "LAYER_NAME", "field_name": "FIELD"})
execute_tool("sample_features", {"layer_name": "LAYER_NAME", "limit": 3})
execute_tool("query_layer", {"layer_name": "Roads", "aggregate": "count"})
execute_tool("query_layer", {"layer_name": "Roads", "aggregate": "count", "filter": "highway = 'motorway'"})
execute_tool("query_layer", {"layer_name": "Cities", "order_by": "population DESC", "limit": 5, "fields": ["name", "population"]})
execute_tool("query_layer", {"layer_name": "Rivers", "order_by": "$length DESC", "limit": 1})
execute_tool("query_layer", {"layer_name": "Lakes and ponds", "aggregate": "sum", "expression": "$area"})
execute_tool("query_layer", {"layer_name": "Roads", "aggregate": "mean", "expression": "$length", "group_by": "highway"})
execute_tool("describe_style", {"layer_name": "LAYER_NAME"})
execute_tool("get_qgis_info", {})
execute_tool("get_canvas_extent", {})
execute_tool("search_processing", {"query": "buffer"})
execute_tool("describe_processing", {"algorithm_id": "native:buffer"})
```

Expectations:

- `get_project_info` returns the layer tree with groups and visibility, the
  units, the themes
- `describe_layer` for a layer in `EPSG:4326` returns `crs_is_geographic: True`,
  `suggested_metric_crs`, plus `provider`, `is_valid` and `style_summary`
- `get_field_values` for a numeric field returns `min`/`max`; for a text field —
  the unique values with a truncation note
- `sample_features` returns real records, long values truncated
- `describe_style` shows the renderer type and the classes with colours
- `describe_processing` returns enums as `{"value": 0, "label": "Round"}` pairs
- a nonexistent layer or field name yields an error with the list of available
  ones
- `query_layer` without `aggregate` returns features; with it — a single number
- `group_by` yields a list of groups with a value and a feature count each
- `$length` and `$area` are measured in the layer's CRS units: on a layer in
  degrees the number is meaningless, and the agent must say so
- an error in an expression yields the parser text, not a crash

### Class branches in describe_style

Categories, graduations and rules cannot be checked on a project with single
symbols only. This snippet installs a categorisation, checks, and puts the
renderer back — nothing remains in the project:

```python
from qgis.core import QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol
from qgis_ai_agent.qgis_tools.registry import execute_tool

layer = QgsProject.instance().mapLayersByName("LAYER_NAME")[0]
saved = layer.renderer().clone()
field = layer.fields().names()[1]
values = list(layer.uniqueValues(layer.fields().indexOf(field)))[:4]
categories = [
    QgsRendererCategory(v, QgsSymbol.defaultSymbol(layer.geometryType()), str(v))
    for v in values
]
layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
print(execute_tool("describe_style", {"layer_name": "LAYER_NAME"}))
print(execute_tool("describe_layer", {"layer_name": "LAYER_NAME"})["style_summary"])
layer.setRenderer(saved)
```

Expectations: `class_attribute`, a `classes` list with a value, a label and a
symbol per class, and a `style_summary` like “categories on field '…',
classes: 4”.

### Secrets in the source

With a PostGIS layer available — verify the password does not leak:

```python
execute_tool("describe_layer", {"layer_name": "POSTGIS_LAYER_NAME"})["source"]
```

The string must contain `password=<hidden>`, not the actual password.

## The agent loop

- **Reading without confirmation.** “what is in my project?” → the agent calls
  `list_layers`, answers from facts, no confirmation buttons appear.
- **Data from the project.** “which fields does layer X have?” →
  `describe_layer`, real fields in the answer.
- **Wording before confirmation.** The agent says “I propose”, never “I created”.
- **Cancel.** Press Cancel → nothing in the project changed.
- **A tool error does not kill the run.** A request with a nonexistent layer →
  the agent sees the error and corrects itself.
- **The turn limit.** A knowingly impossible task → the run stops at
  `MAX_ITERATIONS` with a clear message, QGIS does not hang.

## Skills

- A question about layers needs no `load_skill` — `inspect` is preloaded.
- A processing request → the log shows the `processing` skill loading.
- A question about colours and styling → the `style` skill loads.
- A skill loads once per run.

## Context gathering

- “tell me about my project” → `get_project_info`; the answer carries layer
  groups, what is enabled, the measurement units
- “which values does field X hold” → `get_field_values`, real values
- “why are the cities red” → `load_skill(style)` → `describe_style`; the answer
  names the classification field and the colour, not just “red”
- a broken layer (rename its source file) → `describe_layer` returns
  `is_valid: false`; the agent warns instead of planning on top of it

## Processing and the CRS check

The main scenario the pre-queue validation exists for:

1. “build a 500 m buffer around the cities” on a layer in `EPSG:4326`
2. the first `run_processing` is rejected — the step is marked ✕ in the chat
3. the agent **does not stop**: it reads the error and builds a two-step plan —
   `native:reprojectlayer` → `native:buffer` on its result
4. after confirmation both layers appear, the buffer is geometrically correct

Additionally:

- “find the buffer algorithm” → `search_processing` returns `native:buffer`
- an enum passed as a label instead of an index → the tool coerces it itself

## Transport

- **An endpoint with function calling** — the native path works.
- **An endpoint without it** — the first request fails on `tools`, the adapter
  switches to the JSON protocol, the `supports_tools` flag is written, the next
  requests go straight down the JSON path.
- Changing the URL in the settings does not break the choice: the flag is
  stored under a hash of the URL.

```python
from qgis_ai_agent.core.settings import get_api_url, get_supports_tools
get_supports_tools(get_api_url())
```

## Threads and unloading

- The UI does not freeze during a multi-step run.
- While the batch is applying, the Send button is blocked and the chat shows
  per-step progress.
- Unloading the plugin during an active request does not crash QGIS.

## Conversations

The Conversations button is in the panel header, left of Clear.

1. **A conversation survives a restart.** Ask “what layers do I have?”, wait
   for the reply, close QGIS, open it again, open the plugin → Conversations →
   the list has a row with the question text. Pick it: the whole conversation
   returns.
2. **The model remembers the restored context.** After step 1 ask “and how many
   are there?” — the answer must build on the previous question, not re-ask.
3. **A new conversation drags nothing along.** Conversations → New
   conversation: the feed is empty. Ask something, go back to the previous
   conversation — both are intact and unmixed.
4. **The title is the first message.** A long question is cut with an ellipsis
   and does not break the menu width.
5. **Bound to the project.** Open another QGIS project → Conversations: the
   previous project's conversations are absent. Return the old project — the
   list is back.
6. **Nothing empty accumulates.** Press New conversation five times without
   asking anything → the list does not gain five empty rows.
7. **Switching during a run is forbidden.** Start a long task and, while the
   agent works, press New conversation → the service message says to wait for
   the current task; the feed is not cleared.
8. **Switching with an unapplied plan is forbidden.** Wait for a plan card and,
   without pressing Apply, pick another conversation → a message about the
   planned changes, the card stays, Apply still works.
9. **Clear does not delete the saved copy.** Clear the feed, open
   Conversations → the conversation is still listed and opens with its
   messages.

## Stopping a run

1. **The button changes.** Ask anything: while working, the send button becomes
   a red square with a “Working… press ■ to stop” tooltip.
2. **Stopping is immediate.** Start a long task and press ■ — the panel
   unlocks instantly, without waiting for the model. A “run stopped” message
   appears.
3. **A late reply does not surface.** After stopping, wait a minute: the
   model's answer to the aborted request must not appear retroactively.
4. **Work continues after a stop.** Ask a new question — it goes through
   normally.
5. **Stopping cancels the plan.** Get to a plan card, press ■ (if the run is
   still going) or check that Apply applies nothing after the stop.
6. **Enter during a run corrects instead of queueing.** Start a long task,
   type “actually make it blue, not red”, press Enter → the message appears in
   the feed with a note that it was passed to the agent, and the agent adjusts
   on its next step without restarting the task.

## Changing the styling

Requires a live project with layers. All five tools are writers, so a plan card
with the Apply button must appear every time.

1. **A single colour.** “Make the rivers blue” → a plan card; after Apply the
   layer is recoloured and the legend refreshes without restarting QGIS.
2. **Cancel changes nothing.** Repeat step 1 and press Cancel — the colour is
   unchanged.
3. **Categories.** “Colour the roads by type” → as many categories as the field
   has unique values; the legend shows the value labels.
4. **The default ramp.** The same request without naming a ramp must not fail
   with a ramp error.
5. **A nonexistent ramp.** “Colour by type with the WhateverItWas ramp” — the
   agent receives the available list and retries by itself, without asking the
   user.
6. **Graduations.** “Colour by population, 7 classes, jenks” → seven classes,
   the boundaries are not identical.
7. **A text field in graduations.** “Graduate by name” — the agent must switch
   to categories, not give up.
8. **Labels.** “Label the cities with names” → labels appear. “Remove the
   labels” → they vanish; the symbol styling is untouched.
9. **Opacity.** “Make the basemap 50% transparent” → the layer is see-through,
   the renderer is not reset.
10. **Raster.** Opacity works on a raster layer too.
11. **A colour in words.** “Make the forests dark green” — the agent picks the
    hex itself; no unrecognised-colour error.
12. **Reading before writing.** “Why are the cities red? Make them blue” — the
    feed shows describe_style first, then set_symbol.

## Labels: the text buffer

13. **The buffer switches on.** “Give the city labels a white halo so they stay
    readable” → one step in the plan showing the white text buffer. After
    applying, the labels carry a halo; text size and colour are not reset.
14. **The buffer switches off.** “Remove the label halo” → the halo is gone,
    the labels remain.
15. **Plan steps are distinguishable.** A request changing both the colour and
    the buffer must not produce two identically worded steps.
16. **Duplicates collapse.** If the agent queued the same call twice, the plan
    card shows it once.
17. **The agent does not promise in prose.** A styling request must yield a
    plan card right away, not an “I propose to change…” with zero steps.

## Labels: properties in one call

18. **Font.** “Make the city labels Arial, bold” → one step showing font and
    bold. After applying, the font changed.
19. **Offset.** “Move the city labels 3 mm up” → the labels moved; up is a
    negative offset_y, verify the direction by eye.
20. **Placement.** “Put the labels around the markers, not on top” → placement
    changed to around.
21. **The property catalogue.** “Which label settings exist?” → the agent calls
    describe_style_options and lists real properties, not invented ones.
22. **An unknown property.** Ask for something borderline, e.g. letter-spaced
    labels — the agent either finds the property or honestly says there is
    none, instead of promising in prose.
23. **Everything in one step.** “Label with names, bold, 12 pt, white halo” →
    exactly one step in the card, not four.

## Symbol: properties in one call

24. **Dashes.** “Make the roads grey and dashed” → one step with
    stroke_style=dash; after applying, the lines are dashed.
25. **Marker shape.** “Cities as square markers” → the markers are square.
26. **Outline only.** “Polygons with no fill, outline only” → fill_style=none,
    the outline is visible.
27. **An inapplicable property.** “Make the roads square” → the agent must not
    silently report success: the result carries skipped with a note, and the
    agent tells the user shape does not apply to lines.
28. **The symbol catalogue.** “Which symbol settings exist?” →
    describe_style_options with kind=symbol, real properties listed.

## Project and layers

29. **Loading a layer.** “Load /path/to/file.geojson” → a plan card; after
    applying, the layer is in the tree and on the map.
30. **A nonexistent file.** “Load /no/such.shp” → a clear error about the path,
    nothing queued.
31. **A duplicate name.** Load the same file twice → the agent receives the
    refusal and proposes another name itself instead of retrying.
32. **A group.** “Add the layer to the Background group” → the group was
    created, the layer is inside.
33. **Visibility.** “Hide the roads layer” → the checkbox is off, the map
    repainted.
34. **Renaming.** “Rename the layer to 'City roads'” → the name changed both in
    the tree and in the legend.
35. **Order.** “Move the rivers to the top” → the layer is first in its group
    and draws above the rest.
36. **Back to the root.** Move a layer into a group, then “take it out of the
    group” → the layer is at the tree root.
37. **Zoom.** “Show me the cities layer” → the map fit the extent, no
    confirmation was asked.
38. **Project CRS.** “Switch the project to EPSG:3857” → the map projection
    changed, the layers' own CRS did not.
39. **Saving.** “Save the project” on an already-saved project → written to the
    same place, no asterisk in the window title.
40. **A new project.** “Save the project” on a never-saved one → the agent asks
    for a path instead of inventing one.
41. **Removing a layer.** “Drop layer X” → the layer left the project, the file
    on disk stayed.
42. **The end-to-end scenario.** “Load the file, colour by type, label with
    names and save the project” → one run, all steps in one plan card.

## OpenStreetMap data

Requires internet. Overpass is a public service; a “busy” refusal is not a bug.

43. **Cafes by place name.** “Download the cafes in Tver” → a plan card; after
    applying, a point layer with cafes, more than zero features.
44. **The current view.** Zoom to a small area, “load the buildings in the
    current view” → the agent passes bbox=canvas instead of inventing
    coordinates.
45. **Geometry.** “Download the roads” → a line layer; the agent must not add a
    point layer nobody asked for.
46. **Too wide an extent.** Zoom out to a continent and repeat step 44 → a
    refusal before anything is sent, explaining the five degrees.
47. **A native-language tag value.** “Download amenity=кафе” → an empty result;
    the agent must explain that tags are English, not repeat the request.
48. **A nonexistent place.** “Download the cafes in Nosuchtown” → empty, a
    clear message.
49. **A busy Overpass.** If the service refuses — the agent reports it and
    offers a retry instead of hammering the same request.
50. **The end-to-end scenario.** “Download the parks in Tver, colour them
    green, label with names and save the project” → one run, all steps in one
    card.
51. **Empty sublayers do not arrive.** “Download the cafes in Tver” with
    geometry=all → only the point layer is added; empty lines and polygons are
    dropped.
52. **Several tags at once.** “Download cafes, bars and restaurants in Tver as
    one layer” → one call with selectors and a regex, one point layer.
53. **An exclusion.** “Load the roads except unpaved ones” → selectors with
    `!~`; the result has no highway=track.
54. **Different keys together.** “Shops and cafes” → several selectors in one
    call, not two separate calls.
55. **A selector with no conditions.** Ask to “download everything here” → a
    refusal explaining at least one tag is required.

## Stock QGIS tooling

These verify the agent solves everyday tasks without wandering through search.

56. **The buffer is found first try.** “Build a 500 m buffer around the
    schools” → the feed shows `native:buffer`, not `native:taperedbuffer`.
57. **Area is not an algorithm.** “Compute the area of every polygon” → the
    agent calls `native:fieldcalculator` with `$area`, not
    `native:serviceareafrompoint`.
58. **Length.** “Add a field with line length in kilometres” →
    `$length / 1000`.
59. **Area on a geographic CRS.** The same on a layer in EPSG:4326 → the agent
    reprojects first instead of producing square degrees.
60. **NDVI.** “Compute NDVI for this scene” → `native:rastercalc` with a band
    expression; extent and cell size taken from the raster's `describe_layer`.
61. **Raster clipping.** “Clip the raster by the district boundary” →
    `gdal:cliprasterbymasklayer`.
62. **Zonal statistics.** “Mean elevation per district” →
    `native:zonalstatisticsfb`.
63. **Spatial join.** “Add to the points the name of the district they fall
    in” → `native:joinattributesbylocation`.
64. **Dissolve by field.** “Merge the districts into regions by the region
    field” → `native:dissolve` with the field.
65. **A chain.** “Clip the roads by the city boundary, compute the length and
    save” → all steps in one plan card.
66. **A non-English search request.** The agent must not search for the local
    words — a non-English query returns nothing, it must translate on its own.

## A local model

67. **Connecting without a key.** Start Ollama, set
    `http://localhost:11434/v1`, any installed model, leave the key empty →
    Test connection replies.
68. **A remote address without a key.** Erase the key, put the OpenAI address
    back → a clear message about the key, not about the network.
69. **A run on a local model.** “What layers do I have?” works; if a small
    model fumbles the calls, that is its limit, not a plugin failure.
70. **OpenRouter.** Address `https://openrouter.ai/api/v1`, an OpenRouter key,
    a model like `anthropic/claude-sonnet-4` → Test connection replies, a run
    with tool calls passes.
71. **Anthropic directly.** Address `https://api.anthropic.com/v1`, an
    Anthropic key, format `auto` → the plugin goes to `/messages` on its own,
    tool calls work.
72. **The dialect by hand.** Set format `openai` on the Anthropic address → the
    request goes to `/chat/completions` and the service errors; this verifies
    the manual choice really overrides detection.

## The settings window

73. **The URL fits.** Open the settings: a long gateway address is fully
    visible, no window stretching required.
74. **The preset fills the address.** Pick “Anthropic” → the address and the
    API format filled in, the model field shows a placeholder.
75. **The preset detects back.** Paste the OpenRouter address by hand → the
    provider list selects OpenRouter on its own.
76. **A local provider.** Pick “Ollama” → the key hint changes to “Not
    required”.
77. **The check opens no windows.** Test connection → the result is a line at
    the bottom of the dialog: green on success, red on error. Press it several
    times — no windows stack on the window.
78. **Saving.** Save → the “Settings saved” line, the dialog stays open.
79. **Dark and light themes.** Switch the QGIS theme and open the settings —
    the cards and hints are readable in both.
80. **Input frames are visible.** In the settings, Base URL, Model, API key and
    the drop-downs have an outline; clicking into a field makes the outline
    accented.
81. **Depth is visible.** In the settings the cards are lighter than the window
    background and the inputs darker than the cards — three distinguishable
    levels, not one dark blot.
82. **Header icons.** The three icons — clock, bin, gear — share one colour and
    weight, not mismatched colours. On retina they neither blur nor crop. The
    gear teeth are distinct, not a solid circle.
83. **Icons follow the theme.** Switch the light and dark QGIS themes and
    reopen the panel: the icons are readable in both.

## Interface and answer language

84. **Russian QGIS.** QGIS Settings → General → interface language Russian,
    restart QGIS, open the agent panel: the send button title, the input
    placeholder, Settings, Conversations, Clear conversation — all in Russian.
    This verifies the translator installs before module imports: exactly these
    strings are evaluated at import time.
85. **The settings window in Russian.** Open the settings: Connection,
    Provider, Base URL, API key, Test connection, Save — translated, nothing
    left in English.
86. **The plan card in Russian.** Ask to recolour a layer → the card says “will
    change the project — N steps” with the correct plural form: 1 шаг, 2 шага,
    5 шагов. The buttons are Применить and Отменить; after applying —
    Применено.
87. **The step feed in Russian.** During a run, lines like «Смотрю слои
    проекта.» and «Оформляю «Дороги»: color=blue.» — not English.
88. **English QGIS.** Switch the QGIS language to English, restart: the whole
    plugin interface is English, no Russian remnants.
89. **The model's language follows the user.** In an English QGIS write to the
    agent in Russian → it answers in Russian. In a Russian QGIS write in
    English → it answers in English. The interface does not change either way.
90. **An unsupported QGIS language.** Set, say, German: the plugin interface is
    English (there is no translation), the plugin does not crash, the agent
    answers in English until the user writes otherwise.

## Vision and self-verification

91. **render_map returns a picture.** In the Python console:
    `execute_tool("render_map", {})` → a dict with `width`, `height`, `extent`
    and a non-empty `image_base64`; decoding it yields a valid PNG of the
    current view.
92. **The agent looks at the map.** Ask “what does the map look like?” on a
    vision model → the feed shows render_map, and the answer describes the
    actual colours on screen, not guesses.
93. **A blind endpoint degrades gracefully.** Same question on a model without
    vision → the first request is retried without the image, the run finishes
    with a text note instead of an error, and later runs skip images at once.
94. **Verification runs after Apply.** “Make the rivers blue” → Apply → the
    feed shows “Checking the applied changes…”, then describe_style or
    render_map, then a short verdict that the rivers are now blue.
95. **Verification fixes a failure.** Force one step to fail (e.g. rename the
    layer between queueing and applying) → the verification run sees the
    failure and queues a corrected call; a new plan card appears.
96. **The toggle works.** Untick “Check the result after applying changes” in
    the settings → after Apply no verification run starts.
97. **Verification does not loop.** Apply the plan queued BY a verification
    run → the changes land, and no further verification starts on its own.

## Selection, basemaps, databases, editing

98. **The agent sees the selection.** Select a few features by hand, ask
    “what did I select?” → get_selection lists the layer, the count and real
    attributes.
99. **Computing over the selection.** “Total area of the selected polygons” →
    query_layer with selected_only=true; the number matches the manual check.
100. **Nothing selected is said plainly.** Clear the selection and repeat →
     the agent says nothing is selected instead of computing over everything.
101. **A basemap lands at the bottom.** “Add an OpenStreetMap basemap” → after
     Apply the tile layer sits under all layers and the map shows tiles.
102. **A custom tile URL without {z} is refused** with a clear message before
     anything is queued.
103. **Database connections are read-only discovered.** With a saved PostGIS
     connection, “load roads from the database” walks
     list_db_connections → list_db_tables → add_db_layer and never asks for a
     password in chat.
104. **Editing asks twice.** “Set type to park for the selected features” →
     the plan card, then Apply → an extra warning dialog listing exactly the
     destructive steps. Declining leaves the data untouched.
105. **The edit really lands.** Accepting the dialog changes the values; the
     verification pass re-reads them and confirms the count.
106. **delete_features refuses to delete everything silently.** “Delete all
     features” works only when the filter is the literal all; an empty filter
     is rejected with an explanation.

## Print layouts

107. **A sheet in one run.** “Make an A4 landscape layout with the map, a
     title, a legend and a scale bar” → one plan card; after Apply the layout
     manager holds the sheet and everything sits inside the page.
108. **The agent looks at the sheet.** The verification pass calls
     render_layout; if the legend covers the map, a fix plan appears with
     configure_layout_item.
109. **Legend before map is refused.** Ask for a legend in an empty layout →
     a clear error saying to add a map first, at queue time.
110. **Out-of-page items are refused** at queue time with the page size in
     the message.
111. **Export.** “Export the layout to /tmp/map.pdf” → the file exists and
     opens; a path into a missing folder is refused before queueing.
112. **Item ids are addressable.** describe_layout shows map-1/title;
     “move the title down a little” changes exactly that item.

## Full coverage: python, rasters, fields, services, undo

113. **run_python shows the code first.** “Set a blend mode no tool exposes” →
     the plan card, then Apply → the warning dialog contains the snippet
     itself, readable. Declining runs nothing.
114. **A broken snippet is refused at queue time** with the syntax error and
     the line number, before the user is asked anything.
115. **An endless loop does not hang QGIS.** Queue `while True: pass` → the
     line budget stops it and the agent gets an explanation.
116. **The agent prefers real tools.** “Make the rivers blue” must NOT use
     run_python — the style tools cover it.
117. **Raster pseudocolor.** “Colour the DEM with Viridis” → the ramp covers
     the real min/max of the band, legend shows the classes.
118. **Hillshade.** “Make a hillshade from the DEM” → shaded relief appears;
     azimuth 315 by default.
119. **No-data hiding.** A raster with -9999 filler → “hide the -9999 values”
     makes them transparent and the colours become usable.
120. **Virtual field.** “Add a virtual field with the area in hectares” → the
     column appears in the attribute table, the file on disk is untouched.
121. **Real field, rename, delete.** Add a text field, rename it, delete it →
     the deletion asks the destructive confirmation; a read-only source
     reports a rollback instead of silently failing.
122. **WMS and WFS.** Add a public WMS layer and a WFS layer → tiles draw,
     WFS features are queryable with query_layer.
123. **Undo.** Apply a styling change, then “undo that” → the project returns
     to the previous state; the agent says that data edits are not covered.
124. **Bookmarks and themes.** “Remember this view as centre”, “save this look
     as print” → both appear in list_views and in the QGIS panels.

## Autonomy: staged runs, plan, budget

125. **A whole task in one request.** “Download the cafes of <city> from OSM,
     colour them, label them, make an A4 layout and export it to PDF” → the
     agent plans, queues the download, asks to apply it, then **continues in
     the same run**: reads the new layer, styles it, applies again, builds the
     layout, looks at it, exports. One request, several Apply clicks, no
     re-explaining.
126. **The plan is visible.** During that run the feed shows “Plan 2/5: …”
     lines that advance as steps complete.
127. **Declining a stage stops cleanly.** Press Cancel on a staged plan card →
     the run ends with a message saying the changes were declined; nothing
     half-applied is left behind.
128. **apply_now is not abused.** A single-step request (“make the rivers
     blue”) must still be one plan card at the end, not a staged pause.
129. **The token counter runs.** The header shows a growing token count during
     a run and clears when a new request starts.
130. **The budget stops the run.** Set the budget to something small (say
     5000) in the settings, start a long task → the run stops politely with an
     explanation instead of burning through the key.
131. **A long run does not blow the context.** A 20+ turn run keeps working;
     older tool results come back compacted rather than failing with a
     context-length error from the provider.
132. **Verification iterates.** Force a styling change to land wrongly → the
     verification pass queues a fix, and if that fix also fails the second
     round runs; it stops after three rounds instead of looping forever.

## Onboarding and answering with the map

133. **The empty panel invites.** Open the plugin on a fresh profile with no
     key set → the feed shows a card explaining the key is needed, with a
     button that opens the settings. No cryptic error on the first send.
134. **After saving a key the card changes** to three clickable example
     requests; clicking one sends it as if typed.
135. **Selection as an answer.** “Show me the motorways” → the features are
     selected, the map zooms to them and they flash; the reply names the
     count.
136. **An empty selection is honest.** “Show me the motorways” on a layer
     with none → the agent says nothing matched instead of reporting success.
137. **Layer export.** “Save the roads layer to /tmp/roads.gpkg” → the file
     exists and opens in QGIS; a bad extension is refused before queueing.
138. **Export of the selection.** Select a few features, “export what I
     selected to GeoJSON” → the file holds only those features.

## Correcting mid-run and project memory

139. **Correction lands mid-run.** Start “colour the roads red”, and while it
     works type “actually blue” → the message appears with a note that it was
     passed on, and the agent switches to blue without starting over.
140. **A correction after the run is an ordinary request** — same words typed
     when idle start a new run, not an interjection.
141. **Remembering.** “Remember that POP2020 is the 2020 census” → the plan
     card shows it; after Apply, `list_notes` returns it.
142. **Memory survives a restart and is project-scoped.** Restart QGIS, ask
     “what do you remember?” → the note is there. Open a different project →
     it is not.
143. **Notes reach the model.** With that note stored, ask “what is in
     POP2020?” → the answer uses the remembered meaning without re-reading it
     from you.
144. **Forgetting.** “Forget the POP2020 note” → it is gone from list_notes;
     forgetting something that was never stored is refused with a hint.

## Streaming

145. **The answer grows.** Ask something that needs a long reply — “explain
     what is in this project and what you would fix” → the text appears word
     by word, not all at once after the pause.
146. **Markdown is right at the end.** Ask for an answer with a list and bold
     text → while it streams the formatting may be half-built, but the
     finished message renders as proper markdown, with no stray asterisks.
147. **A tool call drops the draft.** Ask something that makes the agent read
     the project first → whatever it said before the tool disappears when the
     tool line appears; nothing is shown twice.
148. **The saved conversation matches the screen.** After a streamed answer,
     switch to another conversation and back → the reply is there, in one
     copy, exactly as it was read.
149. **An endpoint without SSE still works.** Point the plugin at a server
     that refuses streaming → the answer arrives whole, without an error, and
     the next request goes straight to the ordinary path.
150. **Stop during a stream.** Press ■ while the text is growing → the run
     stops, the draft stops growing and QGIS does not freeze.

## Reasoning models

151. **A local reasoning model does not leak its monologue.** Point the plugin
     at Ollama with a DeepSeek-R1 distill or QwQ, ask anything → the answer is
     the answer; the reasoning sits in its own block, not in the reply text.
152. **The block folds itself away.** While the model reasons the block is open
     and grows; as soon as the answer starts it collapses to one line with the
     elapsed time, and clicking it opens the reasoning again.
153. **DeepSeek shows life while it thinks.** With the DeepSeek endpoint and a
     reasoner model, the block fills during the pause instead of the panel
     sitting still.
154. **Reasoning is not re-sent.** After a reasoning answer, ask a follow-up →
     the token count for the next step does not carry the previous monologue,
     and the model does not refer to it.
155. **A multi-step task with a reasoning model completes.** Ask for something
     that needs tools → each step may show its own block, and the tool calls
     still run in order.
156. **Anthropic extended thinking, off by default.** With the budget left at
     0, Claude answers exactly as before.
157. **Anthropic extended thinking, switched on.** Set the budget to 4096, ask
     for something needing tools → the reasoning block appears, the tools run,
     and the run finishes without an API error about thinking blocks.
158. **A model that cannot think is not broken by the setting.** With a budget
     set, point at a model without extended thinking → the answer still
     arrives, the refusal is remembered and later requests go straight through.

## Streaming on Anthropic

159. **Claude streams too.** With the Anthropic endpoint, ask for a long answer
     → the text grows word by word, exactly as on an OpenAI-compatible one.
160. **Thinking streams with it.** Set the budget to 4096 and ask something
     hard → the reasoning block fills during the pause instead of appearing
     whole at the end, and it reports how long it took.
161. **Tools still work through the stream.** Ask for something needing tools →
     the arguments arrive in pieces but the call runs with the right values,
     and the plan card lists what it should.
162. **The thinking refusal is not confused with a streaming refusal.** With a
     budget set, point at a model without extended thinking → the answer
     arrives streamed; only thinking is switched off, not streaming.

## Asking the user

163. **A real ambiguity becomes a question, not a guess.** With two similarly
     named layers, ask to style "the roads" → the agent asks which one, the
     panel says it waits, and your next message continues the same run.
164. **The answer resumes, not restarts.** After replying, the agent uses the
     answer directly — no re-reading the project from scratch, the task plan
     survives.
165. **No permission questions.** Ordinary requests still end in a plan card,
     never in "shall I proceed?".
