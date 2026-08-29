from qgis_ai_agent.qgis_tools.osm.download_osm import DownloadOsmTool
from qgis_ai_agent.qgis_tools.osm.run_overpass import RunOverpassTool

OSM_TOOLS = [
    DownloadOsmTool(),
    RunOverpassTool(),
]
