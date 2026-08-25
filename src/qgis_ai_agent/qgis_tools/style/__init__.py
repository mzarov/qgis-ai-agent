from qgis_ai_agent.qgis_tools.style.describe_labels import DescribeLabelOptionsTool
from qgis_ai_agent.qgis_tools.style.describe_style import DescribeStyleTool
from qgis_ai_agent.qgis_tools.style.set_categories import SetCategoriesTool
from qgis_ai_agent.qgis_tools.style.set_graduated import SetGraduatedTool
from qgis_ai_agent.qgis_tools.style.set_labels import SetLabelsTool
from qgis_ai_agent.qgis_tools.style.set_opacity import SetOpacityTool
from qgis_ai_agent.qgis_tools.style.set_symbol import SetSymbolTool

STYLE_TOOLS = [
    DescribeStyleTool(),
    DescribeLabelOptionsTool(),
    SetSymbolTool(),
    SetCategoriesTool(),
    SetGraduatedTool(),
    SetLabelsTool(),
    SetOpacityTool(),
]
