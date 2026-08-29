# Data and privacy

QGIS AI Agent runs in QGIS, but a remote language model cannot reason about the
project without receiving context. “Read-only” in the plan means that a tool
does not mutate QGIS. It is not a promise that the tool result remains on the
device.

## Consent and privacy mode

Before the first agent run sends project context to a remote endpoint, the
plugin shows its scheme and host and asks for consent. The decision is stored
separately for each endpoint and can be changed in Settings with **Share project
context with the model provider**. Declining stops that agent run before it
makes a network request. The separate **Test connection** action is an explicit
exception: clicking it sends one short diagnostic request without agent-run
consent.

The separate **Allow sensitive GIS data and tool results** option is off by
default for remote endpoints. It covers feature attribute values, exact map and
layer extents, layer filters and sources, style categories, Processing and
Python results, and rendered map or layout images. While it is off, tools that
can expose those details are omitted from the model's tool schemas and are also
blocked if the model invents a call anyway. Prompts, recent chat, remembered
notes and basic project metadata are still covered by the main consent; they are
not automatically private or safe.

Addresses recognised as local do not show the remote-consent prompt and permit
sensitive tools. A local server can still log or forward data, so review its
configuration.

## What reaches the model endpoint

After the applicable consent, every model turn includes the current prompt, a
recent window of the conversation, a short project context, the loaded skill
instructions and tool schemas. Project notes created with `remember` are
included as well. The main consent can therefore expose basic metadata such as
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

API credentials are stored through the operating system keychain. The plugin
uses the external `keyring` Python library for that integration and does not
write keys to a QGIS project or settings file.

Conversation messages and remembered project notes are stored as plain JSON
under the active QGIS profile in `qgis_ai_agent_sessions`. Atomic writes keep a
previous `.bak` copy so a power loss or partial write does not destroy the last
valid state. These files are not encrypted. Tool results and rendered images
remain in memory unless their content is repeated in a saved chat message or
written by another operation.

## Other network requests

The plugin contains no telemetry. It contacts the model endpoint you configure.
When requested, GIS tools can also contact services such as Overpass, tile
servers, WMS/WFS endpoints or databases selected by the user. QGIS and installed
providers may make their own network requests independently of this plugin.

## Working with sensitive projects

- Prefer a local OpenAI-compatible server whose storage and logging you control.
- Keep sensitive-data sharing disabled unless the task genuinely needs one of
  the detailed result types listed above.
- Ask for schema or aggregates instead of samples when real attribute values are
  not needed.
- Limit requested fields before sampling records.
- Avoid rendering a map when its geography or labels are sensitive.
- Remove saved conversations, project notes and their `.bak` files from the
  QGIS profile when the local record is no longer required.
- Review the configured provider's retention policy before sending client data.
