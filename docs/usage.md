# Usage

Open the panel from the **AI Agent** menu or the toolbar icon, type a request
and press Enter (Shift+Enter starts a new line). While the agent works, the
send button becomes a stop button; Esc stops the run too. A message typed
during a run goes to the agent as a correction.

## Asking about the project

Questions run at once, without confirmation. Above the answer, a folded list
shows each step the agent took and what it found; click it to open.

- *what layers do I have?*
- *which fields does the roads layer have, and what is in `highway`?*
- *which river is the longest?* (lengths and areas come from the geometry)
- *why are the cities red?* (the agent reads the actual style)

## Making changes

Changes collect in a plan card, one numbered step per change. **Apply** runs
them; **Cancel** drops them, and **Restore plan** brings them back until you
send another message. After Apply the card offers **Undo**, which returns the
project to its state before that Apply.

- *make the rivers blue*
- *colour the districts by population, 7 classes, Viridis*
- *label the cities with names, bold, 12 pt, white halo*
- *build a 500 m buffer around the schools* (on a layer in degrees the agent
  reprojects first)
- *download the cafes in Tver from OSM*
- *clip the roads by the city boundary, compute the length and save the
  project* (one plan card for the whole chain)

Long steps, such as Processing algorithms and downloads, run in the
background. QGIS stays usable, the step shows its progress, and ■ stops it and
the steps after it. After Apply the agent checks the result and proposes fixes
if something did not work.

### Questions from the agent

When the agent needs a decision, for example which of two similar layers to
use, it asks in a card with up to three answers and a row for your own. Click
an answer or press its number. The run continues with your answer.

### Modes

The mode button in the chat box switches between three modes. Shift+Tab cycles
through them.

- **Ask** (default): every plan waits for Apply.
- **Auto**: plans apply themselves, web calls included. Plans that edit or
  delete data in place, run Python or run another plugin's code still wait for
  Apply and ask again.
- **Plan**: the agent only reads and answers with a numbered plan. **Run with
  approval** carries it out in Ask mode, **Run automatically** in Auto mode.

## The chat box

- Type `/` to pick a skill: `/osm cafes in Kazan` loads the OSM rules before
  the first step.
- Type `@` to insert an exact layer name, such as `@rivers` or
  `@"Main roads"`.
- The layer selected in QGIS appears above the text. A new request refers to
  it, so *colour this layer* works. Click × to leave it out.
- **+** adds a layer, a file or table, a picture or a skill. **Point on the
  map…** and **Area on the map…** let you click a point or drag a rectangle;
  the place goes into the request as `@point(lon, lat)` or
  `@area(west, south, east, north)`.

Attached or dropped GIS files (GeoPackage, shapefile, GeoJSON, CSV, GeoTIFF
and others) are added to the project at once and named in the request. A CSV
with lon/lat or x/y columns in degrees becomes points; any other CSV becomes a
table. Pictures (PNG, JPEG, WebP, GIF, BMP) go to the model with your next
request; a picture with a world file is added as a layer instead.

## Conversations

Conversations are saved in the QGIS profile and bound to the project. Click
the conversation title at the top to see the history of this project; **+** or
Ctrl+N (⌘N) in the chat box starts a new one. Hover a conversation to rename or
delete it. A reopened conversation keeps the model's context, so follow-up
questions still work.

### Rewinding

Hover one of your messages and click the curved arrow to go back to before
it. Choose **Conversation and project**, **Conversation only** or **Project
only**. The project side restores the snapshot taken before Apply; QGIS keeps
the last ten while it runs. Changes written into data sources are not undone.

### The context window

The ring next to the model name shows how much of the model's context window
the last request used. Click it for details and **Compact**, which replaces
older messages with a summary for the model. The chat keeps every message. A
conversation is compacted on its own at 90 % of the window.

## What the skills add

### Drawing

*Put a point at 55.75, 37.62* or *draw a line from Moscow to Kazan* creates
real features in a scratch layer. Typed pairs are read latitude first. A place
name is geocoded first, which asks for consent. Scratch layers live in memory
until QGIS closes; ask to export one to keep it.

### Tables and joins

The agent previews a CSV (delimiter, encoding, column types, first rows),
loads one as points, or joins it to a layer by a key field. A join is live:
nothing is copied. A join where no key matches is refused with the reason,
such as text against numbers or leading zeros.

### SQL

*How many schools are in each district?* runs one SELECT over the project's
layers and changes nothing. *Make a layer of the districts with their school
counts* keeps the same query as a live virtual layer. Only read queries run.

### Open data

*Find a cloud-free Sentinel-2 image of this area from July* searches the
Microsoft Planetary Computer; *load the clearest one* adds it. Landsat,
elevation models and land cover work the same way. *Add the regions of Kenya*
loads geoBoundaries; Natural Earth layers and public map services (NASA GIBS,
OpenTopoMap, national services) are in the same catalogue. Each download asks
first. **Settings → Connectors** switches sources on and off.

### Charts

*Chart the population by district*, *histogram of parcel areas* or *table of
the ten largest towns* draws a chart or table in the chat. Right-click it to
copy the picture or the data as CSV. The model gets only the numbers.

### Other plugins

The agent can run Processing algorithms of installed plugins as plan steps. A
plugin's menu command runs only after a confirmation. When nothing installed
fits, the agent can search the official plugin repository and install a
plugin after two confirmations; uninstall it in **Plugins → Manage and Install
Plugins**.

## Your own skills

A skill is a `SKILL.md` file with a name, a one-line description and rules. Put
your own in the QGIS profile under `ai_agent_skills/<name>/SKILL.md`.
**Settings → Skills** opens the folder, creates an example and lists any
problems. A local skill can name existing tools but cannot add code. Every
skill, built-in or yours, can be switched off there.

## Settings

- **Connection**: the provider, address, model and key. See [Setup](SETUP.md).
- **Privacy**: where your data goes, SSL checking, how long conversations are
  kept, the run journal (off by default), usage statistics and **Delete
  history and journals**. See [Data and privacy](privacy.md).
- **Advanced**: the check after Apply, the token budget, steps per run (40 by
  default), the tool timeout (120 s), the context window, reasoning, the API
  format and extra request headers. **Reset agent settings** restores the
  defaults but keeps the connection, keys and your texts.
- **Personalisation**: how to address you, answer length and language, units,
  the panel theme, standing instructions and memory notes. All of it goes to
  the model with every request.
- **Skills**, **Connectors** and **Geocoding**: see above.

## When something goes wrong

- A tool error does not end the run; the agent reads it and corrects itself.
- Stop or a failure keeps the partial answer, puts your request back in the
  box and still offers the prepared changes.
- A failed step is marked in the plan with the reason, and the steps after it
  do not run.
- A failed model request shows a card with the cause and, where it helps,
  **Retry**. A busy model is retried automatically.
- Overpass, the OpenStreetMap service, is sometimes busy. Retry later or
  narrow the area.
- Small local models (7–8B) often get tool calls wrong. Use a model of about
  30B or larger with function calling.
