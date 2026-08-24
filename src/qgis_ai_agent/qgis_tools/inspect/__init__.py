from qgis_ai_agent.qgis_tools.inspect.canvas_extent import GetCanvasExtentTool
from qgis_ai_agent.qgis_tools.inspect.describe_layer import DescribeLayerTool
from qgis_ai_agent.qgis_tools.inspect.list_layers import ListLayersTool

INSPECT_TOOLS = [
    ListLayersTool(),
    DescribeLayerTool(),
    GetCanvasExtentTool(),
]
