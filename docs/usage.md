# Usage

Open the panel from the **AI Agent** menu entry or the toolbar icon, type a
request, press Enter. Shift+Enter breaks the line. Type `/` (or use the
skill button under the box) to pick a skill and `@` to pick a layer; both are
highlighted in the text. The model name under the box opens the settings. While the agent
works, a line above the box shows the current step, the send button becomes a
stop button and Esc stops the run too; typing meanwhile corrects the agent.

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

When the agent cannot go on without your decision — which of two similar layers,
which territory — it asks in a card: up to three likely answers to click, and a
fourth row to type your own and press Enter. Typing in the main box works too.
The run continues from the same place with your answer.

### Auto mode

The mode button under the chat box, next to **+**, shows **Ask first** or
**Auto**; click it for the mode menu (number keys choose) or press Shift+Tab in
the box to switch. In Auto the plan card applies itself the
moment it appears — styles, layers, fields, processing, OSM downloads, web
search and page reading included — and the check after it still runs. A batch
with a destructive step (deleting features, overwriting a file, Python code)
waits for **Apply** and its extra confirmation as before, and so does the batch
left over after a failed run. Every applied batch still takes a project
snapshot, so *undo the last change* works the same. The mode is remembered.

### Plan mode

The third mode, **Plan**, changes nothing: the agent may only read — layers,
fields, values, the web — and answers with a numbered plan of the changes it
would make, with exact names and the order. Under the plan two buttons run it:
**Run with approval** (switches to Ask first) or **Run automatically**
(switches to Auto); to change the plan, just reply to it. A step the model tries
to run anyway is refused, not queued. Web search and page reading still ask
for consent per call. Processing algorithms count as changes, even the ones
that only compute statistics, so a plan names them instead of running them;
selecting features or zooming to a layer is allowed, as it leaves the data as
it is.

### Drawing from coordinates

The `draw` skill turns coordinates into real features — with attributes, so
they can be styled, labelled and fed to processing (an annotation is only a
picture on top of the map):

- *put a point at 55.75, 37.62* — typed pairs are read latitude first, the
  usual order on web maps; the agent says which order it took when it is
  unclear
- *add the town hall as a point* — a place or an address is geocoded first,
  which asks for consent like every web request
- *draw a line from Moscow to Kazan* — a straight segment, not a road route
- *a 500 m buffer around this address* — geocode, a point in a metric UTM
  layer and the buffer, in one plan card

By default the features go into a new scratch layer, which lives in memory
until QGIS closes: ask to export it to keep it. Adding to an existing file or
database layer writes into its source, so the plugin asks a second time and
*undo the last change* cannot take it back. Impossible coordinates — a
latitude beyond 90 from a swapped pair, degrees given as metres — are caught
before the plan card appears.

## Conversations

Conversations persist across QGIS restarts and are bound to the project: the
**Conversations** menu lists only the ones started in the currently open
project. After the first answer the model names the conversation in a few words,
as Claude does; until then the title is the start of your first message.
Hovering a conversation in the menu shows a pencil to rename it in place (Enter
keeps, Esc drops — a name you chose is never replaced) and a bin to delete it
for good after a confirmation; deleting the open conversation starts a fresh one.
Restoring a conversation restores the model's context too — a follow-up like
*and how many are there?* keeps working.

### Rewinding to an earlier message

Hover one of your messages and click the curved arrow beside it to go back to
before it, as in Claude Code. You choose what goes back:

- **Conversation and project** — the chat ends just before that message, the
  message returns to the input box to edit or resend, and the project returns
  to how it was before the changes that message led to;
- **Conversation only** — the project stays as it is;
- **Project only** — the chat stays as it is.

The project side uses the snapshots taken before every Apply. They live as long
as QGIS runs and only the newest ten are kept, so an older message may offer the
conversation alone. Edits written into data sources (changed attributes,
deleted features) are not undone; temporary layers too large to copy come back
empty, and the agent says which.

### The context window

The ring next to the model name under the chat box fills with the share of the
model's context window the latest request used; click it for the numbers:

- **Context window** — the latest request against the window, with a bar.
- **… until auto-compact** — how much room is left before the conversation is
  compacted on its own, at 90 % of the window, right before your next request.
- **Compact** — compact now. The model writes a handoff summary (what you
  asked for, what was done with exact layer names, decisions, what is left) and
  from then on reads the summary plus the last exchange instead of the older
  messages. The chat keeps every message and gains a line *Conversation
  compacted · about N tokens saved*; the summary is saved with the conversation.
- **Spent in this conversation** — tokens and requests over the whole
  conversation. Every step of the agent is a request that sends the context
  again, so this is many times the window.

The window size comes from **Settings → Advanced → Context window** when set;
otherwise from the server at the last connection test (OpenRouter and other
`/models` listings, Ollama, LM Studio), otherwise from the model's name,
otherwise 128k.

## Run journals

After an applied run, the conversation shows the path to its plaintext Markdown
journal. It lives in the active QGIS profile's `ai_agent_runs` directory, uses
owner-only permissions where supported and is not removed automatically by the
plugin. It is not encrypted. See
[Data and privacy](privacy.md) for its exact contents and cleanup guidance.

## When something goes wrong

- A tool error does not kill the run: the agent reads the error and corrects
  itself — a wrong layer name gets the list of real ones.
- The stop button aborts the run immediately and discards any planned changes.
- Overpass (the OSM service) is public and sometimes busy; a refusal is not a
  plugin bug — retry later or narrow the query.
- A small local model (7–8B) will fumble the tool calls. The sensible minimum
  is a ~30B-class model with function calling.

## Skills and slash commands

A skill is a knowledge package the agent loads when a task enters its domain:
one `SKILL.md` with a name, a one-line description and the rules in Markdown.
The fourteen built-in skills cover the QGIS domains; you can add your own.

Type `/` in the chat to see the list. Pick a skill with the arrows and Tab, then
write the request: `/osm cafes in Kazan` loads the OSM rules before the first
model turn, so the agent starts in the right domain instead of discovering it a
turn later. A bare `/skill` applies the skill to the current project.

Your own skills live in the QGIS profile, in `ai_agent_skills/<name>/SKILL.md`
— **Settings → Skills** shows the folder, opens it and writes an example to
start from — a `house-style` skill that stays switched off until you edit its
description. The frontmatter needs `name` (lowercase letters, digits, `-` or
`_`) and `description` (the sentence the model picks the skill by); an optional
`tools` list names existing tools to bring along — the domain rules of those
tools load with them. A local skill cannot add Python code: it teaches the
agent your conventions, step order and pitfalls, and it appears in `/` and in
the agent's own `load_skill` list like any built-in one. Problems — a missing
name, a name taken by a built-in skill, an unknown tool — are listed on the
same settings page instead of failing silently.

## Naming layers with @

Type `@` in the chat to pick a layer from the project: the list filters as you
type, ↑↓ or the mouse choose, Tab or Enter insert. The layer name goes into the
request exactly as QGIS knows it — `@rivers`, or `@"Main roads"` when the name
has spaces — so the agent does not have to guess which layer you meant.

## Attaching files

The **+** under the chat box, or dropping files onto it, attaches them.

- **GIS data** (GeoPackage, shapefile, GeoJSON, KML, GPX, CSV, GeoTIFF and the
  like) is added to the project straight away — attaching is your own action,
  like dropping a file onto the map — and the new layer is mentioned in the
  request as `@name`. A name already taken gets a number: `roads (2)`.
  A CSV whose columns are named like lon/lat or x/y and hold degrees becomes
  points in EPSG:4326; any other CSV is added as a table.
- **Pictures** (PNG, JPEG, WebP, GIF, BMP) — a screenshot, a photo of a paper
  map, a sketch — wait above the text and go to the model with your next
  request, their longer side scaled down to 1568 pixels. A picture with a world
  file (`.pgw`, `.jgw`, `.wld`) is georeferenced and is added as a layer
  instead. A model that has already refused images gets none; the chat says so.

## Tables and joins

The `tables` skill handles CSV files and attribute joins:

- “What is in /data/population.csv?” — the agent previews the file: delimiter,
  encoding, columns with the types QGIS will detect, the first rows and the
  columns that look like coordinates.
- “Make points from cafes.csv with lon/lat” — the file is added as a points
  layer linked to the CSV. Degrees get EPSG:4326; projected numbers (UTM, a
  national grid) need the CRS named, and the agent asks rather than guesses.
  Swapped longitude and latitude are refused before anything is added.
- “Attach population.csv to the districts by code” — a live QGIS join: the
  districts gain the table's fields, nothing is copied, and the join is undone
  by asking to remove it. A CSV that is not loaded yet is loaded as a table in
  the same step. Codes with leading zeros (`007`) stay text, and a join where
  no key matches is refused with the reason — text against numbers, leading
  zeros, spaces or letter case. A partial match is reported with the keys that
  found no row.

When the joined fields must become a separate layer or file, ask for that: the
agent then uses the Processing algorithm `native:joinattributestable` instead.

## Charts and tables

Ask for a picture of the data and it appears in the chat:

- “Chart the population by district” — a bar per district, computed in QGIS
  from the layer; long names lay out as rows.
- “Show the distribution of parcel areas” — a histogram of a field or an
  expression such as `$area / 10000`.
- “Pie of land use by area” — shares of a whole; more than seven parts fold
  into “Other”.
- “Table of the ten largest towns with name and population” — a sorted table of
  chosen fields, up to 50 rows.

Hover a bar, point or slice for its value; right-click to copy the picture or
the numbers as CSV. Charts and tables stay with the conversation and come back
when you reopen it. They are drawn for you: the model gets only a short
confirmation with the numbers, not the picture.

## When a run stops or fails

Stop or an error keeps whatever the agent had already written, puts your
request back into the input box so you can resend or edit it, and still shows
the changes the agent had prepared — apply them or dismiss them as usual.
