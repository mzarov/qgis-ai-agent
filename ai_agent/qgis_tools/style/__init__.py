from ai_agent.qgis_tools.style.describe_options import DescribeStyleOptionsTool
from ai_agent.qgis_tools.style.describe_style import DescribeStyleTool
from ai_agent.qgis_tools.style.set_categories import SetCategoriesTool
from ai_agent.qgis_tools.style.set_graduated import SetGraduatedTool
from ai_agent.qgis_tools.style.set_labels import SetLabelsTool
from ai_agent.qgis_tools.style.set_opacity import SetOpacityTool
from ai_agent.qgis_tools.style.set_raster_style import SetRasterStyleTool
from ai_agent.qgis_tools.style.set_symbol import SetSymbolTool

STYLE_TOOLS = [
    DescribeStyleTool(),
    DescribeStyleOptionsTool(),
    SetSymbolTool(),
    SetCategoriesTool(),
    SetGraduatedTool(),
    SetLabelsTool(),
    SetOpacityTool(),
    SetRasterStyleTool(),
]
