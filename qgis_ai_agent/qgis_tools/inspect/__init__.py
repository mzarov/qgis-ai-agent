from qgis_ai_agent.qgis_tools.inspect.canvas_extent import GetCanvasExtentTool
from qgis_ai_agent.qgis_tools.inspect.describe_layer import DescribeLayerTool
from qgis_ai_agent.qgis_tools.inspect.field_values import GetFieldValuesTool
from qgis_ai_agent.qgis_tools.inspect.get_selection import GetSelectionTool
from qgis_ai_agent.qgis_tools.inspect.list_layers import ListLayersTool
from qgis_ai_agent.qgis_tools.inspect.project_info import GetProjectInfoTool
from qgis_ai_agent.qgis_tools.inspect.qgis_info import GetQgisInfoTool
from qgis_ai_agent.qgis_tools.inspect.query_layer import QueryLayerTool
from qgis_ai_agent.qgis_tools.inspect.render_map import RenderMapTool
from qgis_ai_agent.qgis_tools.inspect.sample_features import SampleFeaturesTool

INSPECT_TOOLS = [
    GetProjectInfoTool(),
    ListLayersTool(),
    DescribeLayerTool(),
    GetFieldValuesTool(),
    SampleFeaturesTool(),
    QueryLayerTool(),
    GetSelectionTool(),
    GetCanvasExtentTool(),
    RenderMapTool(),
    GetQgisInfoTool(),
]
