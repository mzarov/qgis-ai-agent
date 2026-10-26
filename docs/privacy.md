# Data and privacy

The agent works by showing your project to the language model you configure.
A "read" tool does not change QGIS, but its result still goes to the model.

## What goes to the model

Every request carries your prompt, the conversation (or its summary after
compaction), a short project context, project notes, your Personalisation
settings, the loaded skill rules and the tool schemas. After each tool call,
the result goes to the model as well. Results can include:

- feature attribute values, unique values and value ranges;
- exact map and layer extents;
- layer filters and data sources;
- style categories;
- Processing and Python results, including paths and error text;
- a PNG image of the map or a print layout, on a model that accepts images;
- pictures you attach.

There is no switch that holds this back: an agent that cannot read the data
cannot do GIS work. Results are shortened to fit the context, but that is not
a privacy boundary. The model also receives the conversation to write a
compaction summary and a short title.

The first send to a remote endpoint asks for confirmation and names its
address. Agreeing is remembered for that endpoint; declining cancels just that
send. Local addresses do not ask. **Test connection** sends one short request
with no project data.

For a project that must not leave your computer, use a local model server
such as Ollama or LM Studio. A local server can still log or forward requests,
so check its configuration.

## Web tools

`search_web`, `geocode` and `fetch_url` ask before each call, also with a local
model. The request starts only after **Apply**. In Auto mode they run without
asking, like the rest of the plan.

- `search_web` sends the search phrase to DuckDuckGo, and to Wikipedia if
  DuckDuckGo fails.
- `geocode` sends the place name to the Photon demo or your own Nominatim
  server, chosen in Settings. Geocoding is off until you choose one. The public
  OSMF server `nominatim.openstreetmap.org` is refused under its
  [usage policy](https://operations.osmfoundation.org/policies/nominatim/).
- `fetch_url` contacts the public HTTPS host in the approved URL.

Only public HTTPS addresses are accepted. Private and local addresses, URLs
with credentials or signatures, and redirects to another origin are refused.
Cookies are not kept. Web results are treated as untrusted data, are passed to
the model and are not saved on disk.

## Other services

When a request needs them, tools also contact:

- the Overpass API for OpenStreetMap data;
- the Microsoft Planetary Computer (the search area and dates; imagery is read
  through a short-lived signed link), GitHub (Natural Earth and geoBoundaries
  files) and the geoBoundaries API (the country code);
- the map services of the open-data catalogue, which receive the extents being
  drawn: NASA GIBS, EOX, GEBCO, OpenTopoMap, IGN France, PDOK, swisstopo, USGS
  and Geoscience Australia;
- plugins.qgis.org, when searching for or installing a plugin. Nothing about
  the project is sent;
- tile, WMS, WFS and database servers you name.

Each of these calls is listed in the plan and asks first, except in Auto mode.
Any open-data source can be switched off in Settings → Connectors. QGIS itself
and its data providers may make their own requests.

## What stays on the computer

API keys are stored in the QGIS authentication database (`qgis-auth.db` in the
active QGIS profile), unlocked by the QGIS master password. Only the entry's
identifier goes into the settings. Extra request headers are plain settings,
so a header whose name suggests a credential (`Authorization`, or a name with
*key*, *token*, *secret*, *password*, *session*, *cookie* or *auth*) is
refused.

Conversations, project notes and memory notes are stored as plain JSON in the
active QGIS profile (`ai_agent_sessions`), with a `.bak` copy of the previous
version. They are not encrypted. Settings → Privacy can delete conversations
untouched for 7 or 30 days.

The run journal is off by default. When you switch it on in Settings →
Privacy, each applied run writes a plaintext Markdown file to `ai_agent_runs`
in the active QGIS profile, and the chat shows its path. It holds shortened
request and agent text, tool names, error text and the outcome. The folder
gets mode `0700` and each file `0600` where the system supports it. That keeps
other local accounts out but is not encrypted. Files stay until you delete
them; **Delete history and journals** in Settings → Privacy removes all
journals and conversations at once.

## Usage statistics

Anonymous usage statistics are on by default. The first time the plugin loads,
a notice in the QGIS message bar says so and offers **Turn off**. Nothing is
counted before that notice. The switch is also in Settings → Privacy; turning
it off deletes the counts not yet sent.

A minute after the counts change, the plugin sends the day so far to the
project's collector on Cloudflare (`telemetry/worker`), which keeps one small
report per install per day: the number of runs and applies, the names of the
plugin's own tools and built-in skills used (never a name the model made up or
a skill you wrote) and how many tool calls failed, the kinds of failures (a
category, an HTTP status with the provider's error code, or an error class
with the plugin file and line, never the error text), the plugin and QGIS
versions, the OS family, the interface language, whether a model is set up,
and whether it is local or remote and which API format it uses. A day QGIS loaded the plugin counts as active even with no
run. A random install id tells installs apart; the collector stores only its
hash. Your IP address is used only to limit how many reports one address can
send a minute and is never stored. Your requests, answers, layer names,
values, places, file paths, keys, model addresses and model names are never
sent. The totals are public on the [usage statistics](usage-stats.md) page.

## Sensitive projects

- Use a local model server whose storage and logging you control.
- Ask for counts and summaries instead of samples when you do not need real
  values.
- Do not render the map when its geography or labels are sensitive.
- Delete saved conversations, notes, `.bak` files and journals when you no
  longer need them.
- Read your provider's data retention policy.
