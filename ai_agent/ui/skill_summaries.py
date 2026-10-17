"""What a person reads about each built-in skill, in their language.

The model chooses skills by the English description in each SKILL.md; the
settings page and the / list show these short translated lines instead. A
skill of the user's own keeps its own description.
"""

from ai_agent.i18n import tr

# What a person reads about each built-in skill; the model reads the English description in SKILL.md.
SUMMARIES = {
    "annotations": tr("Notes and markers on top of the map at a point"),
    "charts": tr("Charts and tables right in the chat: histograms, bars, lines"),
    "data": tr("Open data: imagery, terrain, boundaries, population"),
    "draw": tr("Points, lines and polygons from coordinates in a scratch layer"),
    "edit": tr("Editing and deleting records right in the data source"),
    "fields": tr("Adding, renaming and deleting fields, virtual fields"),
    "inspect": tr("Facts about the project: layers, fields, values, selection"),
    "layout": tr("Print layouts: map, legend, scale; export to PDF and PNG"),
    "osm": tr("OpenStreetMap features through Overpass, as new layers"),
    "plugins": tr("Your other plugins: their algorithms and menu commands"),
    "processing": tr("Geoprocessing: buffers, clipping, overlays, joins and more"),
    "project": tr("Layers, basemaps, web services, groups, bookmarks, saving"),
    "python": tr("PyQGIS code for what no tool covers, shown to you first"),
    "quality": tr("Data checks: broken geometry, duplicates, empty fields, CRS"),
    "sql": tr("SQL across your layers: joins, grouping, live query layers"),
    "style": tr("Symbols, colours by category or class, labels"),
    "tables": tr("CSV preview, tables as points, table joins"),
    "three_d": tr("A 3D view of the map and its terrain"),
    "web": tr("Web search, reading pages, geocoding"),
}


def summary(name: str, description: str) -> str:
    """The person's line for a skill: the translated summary of a built-in one, the description of the user's."""
    return SUMMARIES.get(name, description)
