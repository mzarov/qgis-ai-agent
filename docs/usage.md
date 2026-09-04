# Usage

Open the panel from the **AI Agent** menu entry or the toolbar icon, type a
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
The twelve built-in skills cover the QGIS domains; you can add your own.

Type `/` in the chat to see the list. Pick a skill with the arrows and Tab, then
write the request: `/osm cafes in Kazan` loads the OSM rules before the first
model turn, so the agent starts in the right domain instead of discovering it a
turn later. A bare `/skill` applies the skill to the current project.

Your own skills live in the QGIS profile, in `ai_agent_skills/<name>/SKILL.md`
— **Settings → Skills** shows the folder, opens it and writes an example to
start from. The frontmatter needs `name` (lowercase letters, digits, `-` or
`_`) and `description` (the sentence the model picks the skill by); an optional
`tools` list names existing tools to bring along — the domain rules of those
tools load with them. A local skill cannot add Python code: it teaches the
agent your conventions, step order and pitfalls, and it appears in `/` and in
the agent's own `load_skill` list like any built-in one. Problems — a missing
name, a name taken by a built-in skill, an unknown tool — are listed on the
same settings page instead of failing silently.
