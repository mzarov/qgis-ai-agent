from qgis_ai_agent.qgis_tools.layout.add_label import AddLabelTool
from qgis_ai_agent.qgis_tools.layout.add_legend import AddLegendTool
from qgis_ai_agent.qgis_tools.layout.add_map import AddMapTool
from qgis_ai_agent.qgis_tools.layout.add_scale_bar import AddScaleBarTool
from qgis_ai_agent.qgis_tools.layout.create_layout import CreateLayoutTool

LAYOUT_TOOLS = [
    CreateLayoutTool(),
    AddMapTool(),
    AddLegendTool(),
    AddScaleBarTool(),
    AddLabelTool(),
]
