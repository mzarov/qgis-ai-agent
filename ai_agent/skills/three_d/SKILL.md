---
name: three_d
description: Open a 3D map view. Load this for "show in 3D", "terrain view", "tilt the map". Open the view first; terrain, exaggeration and camera come after it, with run_python from the python skill.
tools: [open_3d_view]
---

# 3D views

Open the view first with `open_3d_view`, and load `python` only afterwards.
Everything inside it — terrain source, vertical exaggeration, camera
position — is adjusted through `run_python` from the `python` skill, because
the 3D API surface is wide and changes between QGIS releases.

Do not write 3D configuration from memory. The reliable route for terrain
from a DEM:
tell the user which DEM layer you would use, open the view, and configure the
terrain with a short `run_python` snippet built around
`Qgs3DMapSettings` — read the current QGIS API docs through `fetch_url`
(`https://qgis.org/pyqgis/master/3d/Qgs3DMapSettings.html`) when unsure,
rather than writing from memory. Terrain needs a DEM raster in the project, and
a project in a geographic CRS gives a flat scene: switch the project to a
projected CRS with `configure_project` first. The project CRS and the DEM layer
are in the project context — when the CRS is projected, open the view at once,
without reading the project or the DEM first.

A 3D view is presentation, not data: it changes nothing in the layers, so a
failed attempt costs nothing but the window.
