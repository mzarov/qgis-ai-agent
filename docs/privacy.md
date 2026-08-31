# Data and privacy

AI Agent runs in QGIS, but a remote language model cannot reason about the
project without receiving context. “Read-only” in the plan means that a tool
does not mutate QGIS. It is not a promise that the tool result remains on the
device.

## Privacy mode

Sending a request shares your prompt and basic project metadata — layer and
field names, CRS, project notes — with the configured endpoint. There is no
separate consent dialog: configuring an endpoint and pressing send is the
decision.

The **Allow sensitive GIS data and tool results** option is off by default for
remote endpoints. It covers feature attribute values, exact map and layer
extents, layer filters and sources, style categories, Processing and Python
results, and rendered map or layout images. While it is off, tools that can
expose those details are omitted from the model's tool schemas and are also
blocked if the model invents a call anyway. Prompts, recent chat, remembered
notes and basic project metadata are not covered by that switch; they travel
with every request and are not automatically private or safe.

Addresses recognised as local permit sensitive tools without the switch. A
local server can still log or forward data, so review its configuration.

## Web tools

The optional `search_web`, `geocode` and `fetch_url` tools have a separate,
per-call consent boundary. Each call is queued in a plan even though it cannot
change the QGIS project; the network request starts only after **Apply** and
**Cancel** discards it. This confirmation is required with both remote and local
model endpoints. A batch containing only web reads does not create a project
snapshot.

The recipients and data are:

- `search_web` sends the search phrase to DuckDuckGo; if that service fails, it
  sends the same phrase to the English or Russian Wikipedia search API;
- `geocode` sends the place name to the Photon demo or custom
  Nominatim-compatible public HTTPS service selected in Settings;
- `fetch_url` sends a request to the public HTTPS host in the URL you approved.

The public OSMF Nominatim instance at `nominatim.openstreetmap.org` is
intentionally rejected rather than offered as generic agent geocoding.
Geocoding starts disabled. The Photon demo preset permits reasonable use, may
throttle heavy traffic and has no availability guarantee; for other use, bring
a service whose operator permits it. Review the official
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).

Web tools accept only public HTTPS destinations. Local, private, link-local and
reserved addresses, credential-bearing or signed URLs, and cross-origin
redirects are rejected. Every DNS answer must be globally routable; one checked
IP is pinned through all same-origin hops while TLS verifies the approved host
name. If a direct connection to one validated address fails, the next validated
answer is tried. When QGIS selects an explicit proxy for the approved host, the
original hostname is sent through that proxy so its rules and DNS path remain
effective; direct routes still use IP pinning and fail closed on a route mismatch.
Cookie persistence and cached HTTP-authentication reuse are
disabled for these requests. Responses are treated as untrusted data, never as
instructions: a page cannot authorise more requests or ask the agent to reveal
prompts, project data, credentials or other tool results.

Search, geocode and fetched-page results become tool results and may therefore
be forwarded to the model endpoint chosen in Settings. The per-call web
confirmation is independent of the model endpoint.

## What reaches the model endpoint

Every model turn includes the current prompt, a
recent window of the conversation, a short project context, the loaded skill
instructions and tool schemas. Project notes created with `remember` are
included as well. A request can therefore expose basic metadata such as
layer names and types even while the sensitive-data option is off.

After a tool runs, its result is returned to the model so it can decide the next
step. With the separate sensitive-data option enabled, tool results can include:

- sampled, queried or selected feature attribute values, unique values and
  numeric ranges;
- exact map and layer extents;
- layer filters and source descriptions;
- style categories;
- Processing and Python results, including output paths or error details;
- a PNG rendering of the map canvas or print layout when image input is enabled.

Tool results are capped or compacted for model context, but truncation is not a
privacy boundary. Do not assume that a sensitive value will be removed.

The connection-test request contains no project context, but the provider may
retain or use it according to its own terms.

## What stays on the computer

API credentials are stored in the QGIS authentication database — the encrypted
`qgis-auth.db` inside the active QGIS profile, the same store QGIS uses for
layer and PostGIS passwords. It is unlocked by the QGIS master password, which
QGIS asks for once per session. The plugin writes no key to a QGIS project or
settings file; only the identifier of the stored entry goes into the settings,
never the secret. Removing the key from the settings window deletes that entry.

Conversation messages and remembered project notes are stored as plain JSON
under the active QGIS profile in `ai_agent_sessions`. Atomic writes keep a
previous `.bak` copy so a power loss or partial write does not destroy the last
valid state. These files are not encrypted. Tool results and rendered images
remain in memory unless their content is repeated in a saved chat message or
written by another operation. Web responses are not cached on disk.

After an applied run, the plugin also writes a plaintext Markdown audit journal
under `ai_agent_runs` in the active QGIS profile and reports the exact path in
the conversation and QGIS log. It records shortened versions of the request and
agent messages, tool names, failed-tool error text, the number of applied steps
and the final outcome. The plugin refuses a symbolic-link journal directory,
sets the directory to owner-only mode `0700` and each atomically written file to
`0600` where the platform supports those permissions. This limits other local
accounts but is not encryption. Journals persist across QGIS restarts and remain
until the user deletes them. They do not add tool arguments or successful
tool-result payloads, but recorded text and errors can still contain sensitive
information.

## Other network requests

The plugin contains no telemetry. It contacts the model endpoint you configure
and the per-call web recipients listed above. When requested, GIS tools can also
contact services such as Overpass, tile servers, WMS/WFS endpoints or databases
selected by the user. QGIS and installed providers may make their own network
requests independently of this plugin.

## Working with sensitive projects

- Prefer a local OpenAI-compatible server whose storage and logging you control.
- Keep sensitive-data sharing disabled unless the task genuinely needs one of
  the detailed result types listed above.
- Ask for schema or aggregates instead of samples when real attribute values are
  not needed.
- Limit requested fields before sampling records.
- Avoid rendering a map when its geography or labels are sensitive.
- Remove saved conversations, project notes and their `.bak` files, and
  Markdown journals from the profile's `ai_agent_runs` directory, when the
  local record is no longer required.
- Review the configured provider's retention policy before sending client data.
