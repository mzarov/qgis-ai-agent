---
name: three_d
description: Open a 3D map view. Load this for "show in 3D", "terrain view", "tilt the map"; terrain, exaggeration and camera are then set with run_python from the python skill.
tools: [open_3d_view]
---

# 3D views

`open_3d_view` opens the window; everything inside it — terrain source,
vertical exaggeration, camera position — is adjusted through `run_python`
from the `python` skill, because the 3D API surface is wide and changes
between QGIS releases.

Do not write 3D configuration from memory. The reliable route for terrain
from a DEM:
tell the user which DEM layer you would use, open the view, and configure the
terrain with a short `run_python` snippet built around
`Qgs3DMapSettings` — read the current QGIS API docs through `fetch_url`
(`https://qgis.org/pyqgis/master/3d/Qgs3DMapSettings.html`) when unsure,
rather than writing from memory. Terrain needs a DEM raster in the project, and
a project in a geographic CRS gives a flat scene: switch the project to a
projected CRS with `configure_project` first.

A 3D view is presentation, not data: it changes nothing in the layers, so a
failed attempt costs nothing but the window.
