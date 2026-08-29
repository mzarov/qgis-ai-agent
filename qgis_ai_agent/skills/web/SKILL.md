---
name: web
description: Look things up on the internet — search the web, read a page, find a place's coordinates and bounding box. Load this when the answer is not in the project.
tools: [search_web, fetch_url, geocode]
---

# The internet

Three tools, in the order you should reach for them.

## geocode first for places

Anything shaped like "where is X" — a town, a street, a landmark — is
`geocode`, not a web search. It answers directly with coordinates and a
bounding box, and the `bbox` string slots straight into `download_osm`. So
"download the cafes in Divnomorskoye" that Overpass does not know by name
becomes: `geocode` the place → `download_osm` with the returned `bbox`.

When several matches come back, pick by the `type` field — a `boundary/administrative`
beats a `place/hamlet` of the same name — and say which one you took.

## search_web for facts, fetch_url for depth

`search_web` returns titles, links and snippets. Snippets alone are often
enough for a short factual answer; when they are not, `fetch_url` the one most
promising link — not all of them. Quote where an answer came from: a claim
from the web without its source is just a rumour with confidence.

`fetch_url` also reads any page the user pastes: documentation, a dataset
description, a service manual. HTML arrives stripped to readable text and
truncated; raise `max_chars` only when the truncation actually cut the answer
off.

## Manners

These are public services without keys. One search per question, one geocode
per place, no retry barrages — a refusal or an empty answer is a reason to
rephrase once, not to hammer. Results can be wrong or stale: prefer the
project's own data when both speak to the same fact, and never present a web
result as something you verified yourself.

The map data behind geocode is © OpenStreetMap contributors — keep that line
when the user asks where numbers came from.
