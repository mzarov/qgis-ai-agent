---
name: osm
description: Download OpenStreetMap data through Overpass and add it to the project as layers — cafes, roads, buildings, water, land use, anything with an OSM key. Load this when the user wants data they do not have yet.
tools: [download_osm]
---

# Data from OpenStreetMap

`download_osm` asks the public Overpass service for objects matching one OSM
key-value pair inside one territory, then adds what came back to the project.

Use it when the user wants data that is not in the project. If the layer already
exists, `inspect` and `processing` are the right skills instead.

## Keys and values are English, always

OSM tags are English regardless of what language the user speaks. "Кафе в Москве"
is `key=amenity`, `value=cafe`, `area=Москва` — the *place name* follows OSM's own
naming, the *tag* never does. Passing `value=кафе` returns nothing.

The tags that cover most requests:

| Ask | key | value |
|---|---|---|
| кафе, рестораны, школы, банки | `amenity` | `cafe`, `restaurant`, `school`, `bank` |
| дороги | `highway` | `primary`, `secondary`, `residential`, `footway` |
| здания | `building` | omit for all buildings, or `yes`, `house` |
| вода | `natural` | `water`; rivers are `waterway=river` |
| зелень, застройка, промзоны | `landuse` | `forest`, `residential`, `industrial` |
| магазины | `shop` | omit for all, or `supermarket`, `bakery` |
| парки, спорт | `leisure` | `park`, `pitch`, `garden` |
| железные дороги | `railway` | `rail`, `station` |

Omitting `value` means "everything with this key" and can be enormous —
`building` over a city is millions of objects. Narrow it or narrow the territory.

## Territory: area or bbox, never both

`area` takes a place name as OSM knows it and is the friendlier option: it follows
real administrative boundaries. If Overpass does not recognise the name, nothing
comes back — try the local spelling or fall back to a bbox.

`bbox` takes `"запад,юг,восток,север"` in degrees, or the literal `"canvas"` for
whatever the user is currently looking at. **`"canvas"` is the right answer to
"здесь", "в этом районе", "в текущем виде"** — do not invent coordinates for it.

A bbox wider than five degrees is refused before anything is sent: Overpass does
not serve requests that size, and a refusal now is better than a timeout later.

## Geometry

One OSM query yields several geometry types — a `highway` search returns both the
road lines and the crossings as points. `geometry` picks what to keep:
`points`, `lines`, `polygons`, or `all`.

Cafes are `points`. Roads are `lines`. Buildings and land use are `polygons`.
Choose deliberately: `all` on a road query adds a points layer the user did not
ask for.

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
