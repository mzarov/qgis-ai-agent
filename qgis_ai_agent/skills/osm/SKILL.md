---
name: osm
description: Download OpenStreetMap data through Overpass and add it to the project as layers — cafes, roads, buildings, water, land use, anything with an OSM key. Load this when the user wants data they do not have yet.
tools: [download_osm]
---

# Data from OpenStreetMap

`download_osm` asks the public Overpass service for objects inside one territory
and adds what came back to the project. It takes the request two ways:

- **`key` plus optional `value`** — one tag, the common case
- **`selectors`** — a list of Overpass selectors, for everything else

You write only *what to select*. The territory binding, the timeout and the output
statements are added by the plugin, so a selector never carries `;`, `out` or `->`
— those are refused.

Use it when the user wants data that is not in the project. If the layer already
exists, `inspect` and `processing` are the right skills instead.

## Keys and values are English, always

OSM tags are English regardless of what language the user speaks. A request for
cafes in Berlin is `key=amenity`, `value=cafe`, `area=Berlin`. When the user writes
in another language, translate the *tag* into English but leave the *place name* as
OSM itself spells it: a translated tag matches nothing at all, and a translated
place name usually does not exist in the data.

The tags that cover most requests:

| Ask | key | value |
|---|---|---|
| cafes, restaurants, schools, banks | `amenity` | `cafe`, `restaurant`, `school`, `bank` |
| roads | `highway` | `primary`, `secondary`, `residential`, `footway` |
| buildings | `building` | omit for all buildings, or `yes`, `house` |
| water | `natural` | `water`; rivers are `waterway=river` |
| greenery, housing, industry | `landuse` | `forest`, `residential`, `industrial` |
| shops | `shop` | omit for all, or `supermarket`, `bakery` |
| parks, sport | `leisure` | `park`, `pitch`, `garden` |
| railways | `railway` | `rail`, `station` |

Omitting `value` means "everything with this key" and can be enormous —
`building` over a city is tens of thousands of objects. Narrow it or narrow the
territory.

## Anything the pair cannot say

Reach for `selectors` the moment the request needs more than one tag. Each entry
is `<element>` followed by conditions, where element is `node`, `way`, `relation`
or `nwr` for all three:

| Ask | selectors |
|---|---|
| cafes, bars and restaurants as one layer | `['node["amenity"~"cafe\|bar\|restaurant"]']` |
| shops and cafes together | `['node["shop"]', 'way["shop"]', 'node["amenity"="cafe"]']` |
| roads except tracks and paths | `['way["highway"]["highway"!~"track\|path\|footway"]']` |
| buildings that state their floor count | `['way["building"]["building:levels"]']` |
| anything named "Central" | `['nwr["name"~"Central"]']` |

The operators are Overpass's own: `=` equals, `!=` differs, `~` matches a regular
expression, `!~` does not match, and a bare `["key"]` means the tag is present
whatever its value.

A selector with no condition at all is refused — `node` alone would drag down
everything in the territory.

When you use `selectors`, you choose the element types yourself, so `geometry`
only decides which of the resulting layers to keep.

## Territory: area or bbox, never both

`area` takes a place name as OSM knows it and is the friendlier option: it follows
real administrative boundaries. If Overpass does not recognise the name, nothing
comes back — try the local spelling or fall back to a bbox.

`bbox` takes `"west,south,east,north"` in degrees, or the literal `"canvas"` for
whatever the user is currently looking at. **`"canvas"` is the right answer to
"here", "in this area", "in the current view"** — do not invent coordinates for it.

A bbox wider than five degrees is refused before anything is sent: Overpass does
not serve requests that size, and a refusal now is better than a timeout later.

## Geometry

One OSM query yields several geometry types — a `highway` search returns both the
road lines and the crossings as points. `geometry` picks what to keep:
`points`, `lines`, `polygons`, or `all`.

**Pick one deliberately instead of leaving `all`.** `all` on a cafe search adds
three empty layers alongside the one the user wanted; on a road search it adds a
points layer of traffic signals nobody asked for. Cafes and shops are `points`,
roads and rivers are `lines`, buildings and land use are `polygons`.

Each geometry becomes its own layer, because QGIS cannot mix geometry types in one
vector layer. The result lists exactly what was added and how many objects are in
each.

## What can go wrong

Overpass is a free public service. It is often busy, and a rejection is not a bug
in the request — say so plainly and offer to retry or narrow the query rather than
firing the same thing again.

An empty result usually means the tag is wrong, not that the area is empty. Check
the key and value against the table above before blaming the territory.

## After downloading

The layers arrive with QGIS's default styling, which for OSM data is close to
useless — every road the same thin line. Downloading is rarely the whole task:
if the user asked to see something, follow up with the `style` skill, and with
`project` to save the result.
