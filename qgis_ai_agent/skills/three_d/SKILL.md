---
name: three_d
description: 3D map views — open one and shape its terrain, camera and exaggeration. Load this for "show in 3D", "terrain view", "tilt the map".
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
(`https://qgis.org/pyqgis/` plus the class name) when unsure, rather than
writing from memory.

A 3D view is presentation, not data: it changes nothing in the layers, so a
failed attempt costs nothing but the window.
