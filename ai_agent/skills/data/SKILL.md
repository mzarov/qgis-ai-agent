---
name: data
description: Find and fetch open data the project lacks — satellite images (Sentinel-2, Landsat), elevation, land cover, surface water, world base layers, administrative boundaries. Load this when the user needs data that is neither in the project nor on disk, other than OSM features.
tools: [find_open_data, search_imagery, load_imagery, load_dataset]
---

# Open data and imagery

The plugin knows a fixed catalogue. `find_open_data` lists it offline — call it
first when you are not sure which dataset fits; each entry says how to load it.

## Two kinds of data, two paths

- **Vector sets** (`natural-earth`, `geoboundaries`): one call to `load_dataset`.
  Natural Earth is the world at small scale — countries, provinces, cities,
  rivers, coastline; pick `scale` 110m for a world map, 50m for a continent,
  10m for a country. geoBoundaries is one country's administrative units:
  `country` is the ISO alpha-3 code (FRA, KEN, RUS), `level` ADM1 for regions,
  ADM2 for districts.
- **Imagery and rasters** (Sentinel-2, Landsat, Copernicus DEM, WorldCover,
  land use, surface water): `search_imagery` over an area, then `load_imagery`
  with the scene ids it returned. Never invent a scene id.

## Searching scenes

- The area is `bbox` in degrees, `bbox="canvas"` for the current view, or
  `layer_name` for a layer's extent. A place name is not an area: get its
  coordinates first (geocode in the web skill) or zoom there.
- Optical scenes (Sentinel-2, Landsat) are sorted clearest first under
  `max_cloud` (default 20 %). Give `date_from`/`date_to` for a season; for
  "the latest image" pass `newest_first`.
- Elevation, WorldCover and surface water are timeless tiles: leave the dates out.
- A scene or tile covers about 1°×1° (Sentinel-2 about 110 km), and a scene at
  the edge of a satellite pass holds data in a sliver only. Each scene says
  `covers_area_percent`; scenes covering the whole area come first. Prefer one
  near 100 %; when none covers the area, load the tiles that together cover
  it, not just the first.

## Loading

- Defaults are the useful picture: Sentinel-2 `visual` and Landsat `true_color`
  are ready true-colour images; DEMs load heights. Ask for single bands
  (`B04` red, `B08` near infrared for Sentinel-2; `red`, `nir08` for Landsat)
  only when the user wants to compute something such as NDVI — then hand the
  bands to the processing skill (raster calculator).
- Imagery is read in place over the internet through a signed link that expires
  within a day. Tell the user once, and offer `export_layer` when they want to
  keep the data or analyse it heavily.
- Repeat the dataset's licence to the user when it asks for attribution
  (Copernicus, ESA WorldCover, geoBoundaries per country).

## Not here

OpenStreetMap features (buildings, shops, roads by tag) are the osm skill.
Background maps to look at are `add_basemap` in the project skill.
