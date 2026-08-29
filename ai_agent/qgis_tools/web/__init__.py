from ai_agent.qgis_tools.web.fetch_url import FetchUrlTool
from ai_agent.qgis_tools.web.geocode import GeocodeTool
from ai_agent.qgis_tools.web.search_web import SearchWebTool

WEB_TOOLS = [
    SearchWebTool(),
    FetchUrlTool(),
    GeocodeTool(),
]
